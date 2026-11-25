"""Desktop presentation helpers, independent of Tk."""
import errno

def explain_error(exc):
    raw=str(exc) or type(exc).__name__
    if isinstance(exc,PermissionError):
        hint='Some paths are protected or in use. Choose a folder you can read; administrator access is not required for ordinary projects.'
    elif isinstance(exc,FileNotFoundError):
        hint='The selected file or folder is missing. Choose an existing path and try again.'
    elif isinstance(exc,OSError) and (exc.errno==errno.ENOSPC or getattr(exc,'winerror',None)==112):
        hint='The destination has insufficient free space. Free space or choose another destination.'
    else:
        return raw
    return hint+'\nDetails: '+raw
