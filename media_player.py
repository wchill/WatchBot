import asyncio
import os
import re

import ffmpy3
from pymediainfo import MediaInfo

import ruamel.yaml
CONFIG_FILE = 'config.yaml'

with open(CONFIG_FILE, 'r') as f:
    settings = ruamel.yaml.load(f.read(), ruamel.yaml.RoundTripLoader)

FONT_FILE = settings['ffmpeg']['font_file']


class DiscordMediaPlayer(object):

    TOTAL_DURATION_REGEX = re.compile(r'Duration: (?P<hrs>[\d]+):(?P<mins>[\d]+):(?P<secs>[\d]+)\.(?P<ms>[\d]+)')
    CURRENT_PROGRESS_REGEX = re.compile(r'time=(?P<hrs>[\d]+):(?P<mins>[\d]+):(?P<secs>[\d]+)\.(?P<ms>[\d]+)')

    def __init__(self, stream_url):
        self._stream_url = stream_url
        self._ffmpeg_process = None
        self._current_time = None
        self._total_duration = None

    @staticmethod
    def get_human_readable_track_info(file_path):
        mi = MediaInfo.parse(file_path)
        audio_tracks, subtitle_tracks = [], []
        for track in mi.tracks:
            if track.track_type == 'Audio':
                audio_tracks.append(
                    '#{num}: {name} ({lang}, {codec} - {channels})'.format(
                        num=track.stream_identifier + 1,
                        name=track.title or 'Untitled',
                        lang=track.other_language[0] or 'Unknown language',
                        codec=track.format or 'Unknown codec',
                        channels=(str(track.channel_s) or 'Unknown') + ' channels'
                    )
                )
            elif track.track_type == 'Text':
                subtitle_tracks.append(
                    '#{num}: {name} ({lang})'.format(
                        num=track.stream_identifier + 1,
                        name=track.title or 'Untitled',
                        lang=track.language or 'Unknown language'
                    )
                )

        return audio_tracks, subtitle_tracks

    @staticmethod
    def convert_to_secs(hrs, mins, secs, ms):
        return int(hrs) * 3600 + int(mins) * 60 + int(secs) + int(ms) * 0.01

    @staticmethod
    def convert_secs_to_str(secs):
        hrs, secs = int(secs // 3600), secs % 3600
        mins, secs = int(secs // 60), secs % 60
        if hrs > 0:
            return '{}:{:02d}:{:05.2f}'.format(hrs, mins, secs)
        else:
            return '{}:{:05.2f}'.format(mins, secs)

    def is_video_playing(self):
        return self._ffmpeg_process is not None

    def get_video_time(self):
        return self._current_time, self._total_duration

    async def stop_video(self):
        if self._ffmpeg_process and self._ffmpeg_process.process.returncode is None:
            try:
                self._ffmpeg_process.process.terminate()
            except ffmpy3.FFRuntimeError:
                pass

        if not self._ffmpeg_process or not self._ffmpeg_process.process:
            exitcode = None
        else:
            exitcode = self._ffmpeg_process.process.returncode

        current, total = self.get_video_time()
        return exitcode, current, total

    async def play_video(self, file_path, selected_audio_track=1, selected_subtitle_track=None, seek_time=0):
        if not os.path.exists(file_path):
            raise FileNotFoundError('File not found: {}'.format(file_path))

        if self._ffmpeg_process:
            self.stop_video()

        output_params = [
            # Tell ffmpeg to start encoding from seek_time seconds into the video
            '-ss', str(seek_time),

            # Input file
            '-i', file_path,

            # Select the first video track (if there are multiple)
            '-map', '0:v:0',

            # Select the specified audio track (if there are multiple) - note that it's 0 indexed
            '-map', '0:a:{}'.format(selected_audio_track - 1)
        ]

        # Build filtergraph
        # First filter: change frame timestamps so that they are correct when starting at seek_time
        vf_str = 'setpts=PTS+{}/TB,'.format(seek_time)

        # Second filter: render embedded subtitle track from the media file
        # Note that subtitles rely on the above timestamps and that tracks are 0 indexed
        if selected_subtitle_track:
            vf_str += 'subtitles=\'{}\':si={},'.format(file_path, selected_subtitle_track - 1)

        # Third filter: Draw timestamp for current frame in the video to make seeking easier
        # TODO: make these parameters more configurable
        vf_str += 'drawtext=\'fontfile={}: fontcolor=white: x=0: y=h-line_h-5: fontsize=24: boxcolor=black@0.5: box=1: text=%{{pts\\:hms}}\''.format(FONT_FILE)

        # TODO: make these more configurable
        output_params += [
            # Filtergraph options from above
            '-vf', vf_str,

            # Use the following encoding settings:

            # Encode using x264 veryfast preset (decent performance/quality for realtime streaming)
            '-vcodec', 'libx264',
            '-preset', 'veryfast',

            # Specify max bitrate of 4.5Mbps with buffer size of 1.125Mbps (0.25 sec buffer for faster stream startup)
            '-maxrate', '4500k',
            '-bufsize', '1125k',

            # Use YUV color space, 4:2:0 chroma subsampling, 8-bit render depth
            '-pix_fmt', 'yuv420p',

            # Set keyframe interval to 24
            # (RTMP clients need to wait for the next keyframe, so this is a 1 second startup time)
            '-g', '24',

            # Use AAC-LC audio codec, 128Kbps stereo at 44.1KHz sampling rate
            '-c:a', 'libfdk_aac',
            '-ab', '128k',
            '-ac', '2',
            '-ar', '44100',

            # Some more options to reduce startup time
            '-probesize', '32',
            '-analyzeduration', '500000',
            '-flush_packets', '1',

            # Output format is FLV
            '-f', 'flv'
        ]

        self._ffmpeg_process = ffmpy3.FFmpeg(
            # Read input file at the frame rate it's encoded at (crucial for live streams and synchronization)
            global_options=[
                '-re'
            ],
            inputs={file_path: None},
            outputs={self._stream_url: output_params},
        )

        await self._ffmpeg_process.run(stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        line_buf = bytearray()

        while True:
            in_buf = await self._ffmpeg_process.process.stderr.read(128)
            if not in_buf:
                break
            in_buf = in_buf.replace(b'\r', b'\n')
            line_buf.extend(in_buf)

            while b'\n' in line_buf:
                line, _, line_buf = line_buf.partition(b'\n')
                line = str(line)

                if self._total_duration is None:
                    match = self.TOTAL_DURATION_REGEX.search(line)
                    if match:
                        self._total_duration = self.convert_to_secs(**match.groupdict())
                else:
                    match = self.CURRENT_PROGRESS_REGEX.search(line)
                    if match:
                        self._current_time = self.convert_to_secs(**match.groupdict())

        return self.stop_video()
