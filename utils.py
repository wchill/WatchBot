import re
import humanize

async def ask_for_int(bot, message, author, lower_bound=None, upper_bound=None, timeout=30, timeout_msg=None, default=None):
    def check(msg):
        s = msg.content
        if not s.isdigit():
            return False
        n = int(s)
        if lower_bound is not None and lower_bound > n:
            return False
        if upper_bound is not None and upper_bound < n:
            return False
        return True

    await bot.say(message)
    message = await bot.wait_for_message(timeout=timeout, author=author, check=check)

    if message is None:
        if not timeout_msg:
            timeout_msg = 'No response received within 30 seconds. Using default value.'
        await bot.say(timeout_msg)
        return default

    return int(message.content)


def escape_msg(msg):
    return re.sub(r'(?P<c>[`*_\[\]~])', r'\\\g<c>', msg)


def escape_code_block(msg):
    return re.sub(r'(?P<a>`)(?P<b>`)(?P<c>`)', r'\\\g<a>\\\g<b>\\\g<c>', msg)


def parse_timestamp(time_str):
    match = re.search(r'(?:(\d+):)?(?:(\d+):)?(?:(\d+)(?:\.(\d+))?)', time_str)
    if match:
        hrs, mins, secs, ms = match.group(1, 2, 3, 4)
        if hrs and mins is None:
            mins = hrs
            hrs = None
        hrs = int(hrs) if hrs else 0
        mins = int(mins) if mins else 0
        secs = int(secs)
        ms = int(ms) if ms else 0
        time = 3600 * hrs + 60 * mins + secs + 0.01 * ms
        return time
    return None


def format_dir_entry(num, max_num, entry):
    return '{pad}{num}) {name}'.format(num=num, pad=(len(str(max_num)) - len(str(num))) * ' ', name=escape_code_block(entry.name))


def format_file_entry(num, max_num, entry):
    MAX_WIDTH = 78
    entry_str = '{pad}{num}) '.format(num=num, pad=(len(str(max_num)) - len(str(num))) * ' ')
    name_split = escape_code_block(entry.name).split(' ')

    all_strs = [entry_str]
    current_width = len(entry_str)

    for s in name_split:
        remaining = MAX_WIDTH - current_width
        all_strs.append('{} '.format(s))
        if remaining == len(s):
            current_width = 0
        elif remaining > len(s):
            current_width += len(s) + 1
        else:
            current_width = (len(s) + 1) % MAX_WIDTH

    size_str = humanize.naturalsize(entry.stat().st_size)

    all_strs.append(' ' * (MAX_WIDTH - current_width - len(size_str)))
    all_strs.append(size_str)
    return ''.join(all_strs)
