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


class Video(object):

    def __init__(self, absolute_path, name=None, seek_time=0.0, audio_track=1, subtitle_track=None):
        self.filename = os.path.basename(absolute_path)
        self.name = name if name else os.path.splitext(self.filename)[0]
        self.absolute_path = absolute_path
        self.seek_time = seek_time
        self.audio_track = audio_track
        self.subtitle_track = subtitle_track


class DiscordMediaPlayer(object):

    TOTAL_DURATION_REGEX = re.compile(r'Duration: (?P<hrs>[\d]+):(?P<mins>[\d]+):(?P<secs>[\d]+)\.(?P<ms>[\d]+)')
    CURRENT_PROGRESS_REGEX = re.compile(r'time=(?P<hrs>[\d]+):(?P<mins>[\d]+):(?P<secs>[\d]+)\.(?P<ms>[\d]+)')

    def __init__(self, stream_url):
        self._stream_url = stream_url
        self._ffmpeg_process = None
        self._offset_time = 0
        self._total_duration = None
        self._current_video = None

    @staticmethod
    def get_human_readable_track_info(file_path):
        mi = MediaInfo.parse(file_path)
        audio_tracks, subtitle_tracks = [], []
        for track in mi.tracks:
            if track.track_type == 'Audio':
                audio_tracks.append(
                    '{num}) {name} ({lang}, {codec} - {channels})'.format(
                        num=track.stream_identifier + 1,
                        name=track.title or 'Untitled',
                        lang=track.other_language[0] or 'Unknown language',
                        codec=track.format or 'Unknown codec',
                        channels=(str(track.channel_s) or 'Unknown') + ' channels'
                    )
                )
            elif track.track_type == 'Text':
                subtitle_tracks.append(
                    '{num}) {name} ({lang})'.format(
                        num=track.stream_identifier + 1,
                        name=track.title or 'Untitled',
                        lang=track.other_language[0] or 'Unknown language'
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
        return self._ffmpeg_process and self._ffmpeg_process.process.returncode is None

    def get_video_time(self):
        return self._current_video.seek_time + self._offset_time, self._total_duration

    def get_current_video(self):
        return self._current_video

    async def stop_video(self):
        if self.is_video_playing():
            try:
                print('Stopping FFmpeg')
                self._ffmpeg_process.process.terminate()
                await self._ffmpeg_process.process.wait()
            except ffmpy3.FFRuntimeError:
                pass

        if not self._ffmpeg_process or not self._ffmpeg_process.process:
            exitcode = None
        else:
            exitcode = self._ffmpeg_process.process.returncode

        current, total = self.get_video_time()
        return exitcode, current, total

    async def play_video(self, video):
        if not os.path.exists(video.absolute_path):
            raise FileNotFoundError('File not found: {}'.format(video.filename))

        self._current_video = video

        output_params = [
            # Select the first video track (if there are multiple)
            '-map', '0:v:0',

            # Select the specified audio track (if there are multiple) - note that it's 0 indexed
            '-map', '0:a:{}'.format(video.subtitle_track - 1)
        ]

        # Build filtergraph
        # First filter: change frame timestamps so that they are correct when starting at seek_time
        vf_str = 'setpts=PTS+{}/TB,'.format(video.seek_time)

        # Second filter: render embedded subtitle track from the media file
        # Note that subtitles rely on the above timestamps and that tracks are 0 indexed
        if video.subtitle_track:
            vf_str += 'subtitles=\'{}\':si={},'.format(video.absolute_path, video.subtitle_track - 1)

        # Third filter: Draw timestamp for current frame in the video to make seeking easier
        # TODO: make these parameters more configurable
        vf_str += 'drawtext=\'fontfile={}: fontcolor=white: x=0: y=h-line_h-5: fontsize=24: boxcolor=black@0.5: box=1: text=%{{pts\\:hms}}\','.format(FONT_FILE)
        vf_str += 'setpts=PTS-STARTPTS'

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
            global_options=[
                # Tell ffmpeg to start encoding from seek_time seconds into the video
                '-ss', str(video.seek_time),

                # Read input file at the frame rate it's encoded at (crucial for live streams and synchronization)
                '-re',
            ],
            inputs={video.absolute_path: None},
            outputs={self._stream_url: output_params},
        )

        print('Starting FFmpeg')
        print(self._ffmpeg_process.cmd)

        # Start FFmpeg, redirect stderr so we can keep track of encoding progress
        await self._ffmpeg_process.run(stderr=asyncio.subprocess.PIPE)

        # Buffer for incomplete line output
        line_buf = bytearray()

        my_stderr = self._ffmpeg_process.process.stderr

        while True:
            # Read some FFmpeg output (128 bytes is about 1 line worth)
            in_buf = await my_stderr.read(128)

            # Break if EOF
            if not in_buf:
                break

            # FFmpeg encoding progress is displayed on the same line using CR, so replace with LF if present
            in_buf = in_buf.replace(b'\r', b'\n')

            # Append to the buffer
            line_buf.extend(in_buf)

            # Process each line present in the buffer
            while b'\n' in line_buf:
                line, _, line_buf = line_buf.partition(b'\n')
                line = str(line)
                # print(line)

                if self._total_duration is None:
                    # Get total video duration
                    match = self.TOTAL_DURATION_REGEX.search(line)
                    if match:
                        self._total_duration = self.convert_to_secs(**match.groupdict())
                else:
                    # Get current video playback duration
                    match = self.CURRENT_PROGRESS_REGEX.search(line)
                    if match:
                        self._offset_time = self.convert_to_secs(**match.groupdict())

        # At this point, FFmpeg will already have stopped without us having to wait explicitly on it
        # because it will close stderr when it is complete (breaking the loop)
        print('FFmpeg finished')
        return self._ffmpeg_process.process.returncode
