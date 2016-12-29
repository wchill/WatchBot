import re

async def ask_for_int(client, message, channel, author, lower_bound=None, upper_bound=None, timeout=30, timeout_msg=None, default=None):
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

    await client.send_message(channel, message)
    message = await client.wait_for_message(timeout=timeout, author=author, check=check)

    if message is None:
        if not timeout_msg:
            timeout_msg = 'No response received within 30 seconds. Using default value.'
        await client.send_message(channel, timeout_msg)
        return default

    return int(message.content)


def escape_msg(msg):
    return re.sub(r'(?P<c>[`*_\[\]~])', r'\\\g<c>', msg)