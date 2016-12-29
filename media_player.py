import asyncio
import os

import ffmpy
from pymediainfo import MediaInfo

import ruamel.yaml
CONFIG_FILE = 'config.yml'

with open(CONFIG_FILE, 'r') as f:
    settings = ruamel.yaml.load(f.read(), ruamel.yaml.RoundTripLoader)

FONT_FILE = settings['ffmpeg']['font_file']

class DiscordMediaPlayer(object):

    def __init__(self, stream_url):
        self._stream_url = stream_url
        self._ffmpeg_process = None

    def get_human_readable_track_info(self, file_path):
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

    def is_video_playing(self):
        return self._ffmpeg_process is not None

    async def stop_video(self):
        exitcode = None
        if self._ffmpeg_process:
            try:
                self._ffmpeg_process.process.terminate()
            except ffmpy.FFRuntimeError:
                pass

            exitcode = self._ffmpeg_process.process.returncode
            self._ffmpeg_process = None
        return exitcode

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

            # Set keyframe interval to 24 (RTMP clients need to wait for the next keyframe, so this is a 1 second startup time)
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

        self._ffmpeg_process = ffmpy.FFmpeg(
            # Read input file at the frame rate it's encoded at (crucial for live streams and synchronization)
            global_options=[
                '-re'
            ],
            inputs={file_path: None},
            outputs={self._stream_url: output_params}
        )

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._ffmpeg_process.run)
        except ffmpy.FFRuntimeError:
            pass
        return self.stop_video()