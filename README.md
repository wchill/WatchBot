# discord-rtmp-bot
Discord chat bot used to stream VODs to an RTMP server

## Installation
Install `ffmpeg`. You will probably need to compile using this guide: https://trac.ffmpeg.org/wiki/CompilationGuide/Ubuntu At minimum, you should install `yasm`, `libx264`, and `libfdk-aac` as dependencies while compiling.

Install `mediainfo`.

Set up a new virtualenv: `python3 -m virtualenv -p /usr/bin/python3.5 env`

Install Python dependencies: `python3 -m pip install -r requirements.txt`

Make a copy of `config.yaml.example` and configure it to your needs. You will need an RTMP server to stream to as well as a Discord API key for a bot account.

## Usage
To be completed
