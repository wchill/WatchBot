import os

def is_safe_path(basedir, path, follow_symlinks=True):
    # resolves symbolic links
    if follow_symlinks:
        return os.path.realpath(path).startswith(basedir)

    return os.path.abspath(path).startswith(basedir)


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
            timeout_msg = 'No response received within 30 seconds. Cancelling stream.'
        await client.send_message(channel, timeout_msg)
        return default

    return int(message.content)