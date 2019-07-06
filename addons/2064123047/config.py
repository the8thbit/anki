from aqt import mw
userOption = None
from .debug import debugFun, debug

def getUserOption():
    global userOption
    if userOption is None:
        userOption = mw.addonManager.getConfig(__name__)
        debug("Reading userOption in file.")
        debug("{userOption}")
    return userOption

@debugFun
def getConfig(key, default = None, mid = None, windowName = None):
    options = getUserOption()
    if mid is not None:
        mid = str(mid)
        debug("mid is {mid}")
        if "mids" not in options:
            debug("mids not in the options")
            options["mids"] = dict()
        options = options["mids"]
        debug("mids's option is: {options}")
        if mid not in options:
            debug("mid {mid} not in the options")
            options[mid] = dict()
        options = options[mid]
        debug("mid's option is: {options}")
    else:
        debug("mid is None, thus options does not change")
    if windowName is None:
        debug("windowName is None, thus options does not change")
    elif getConfig("same config for each window",True):
        debug("'same config for each window' is either absent or True")
    else:
        if windowName not in options:
            debug("windowName {windowName} not in the options")
            options[windowName] = dict()
        options_window = options[windowName]
        debug("windowName's options are {options}")
        if key not in options_window and key in options:
            debug("key {key} not in the options_window, but in last options, thus returning the key associated to last options {options[key]}")
            return options[key]
        debug("key {key}  in the options_window or not in last options. Options becomes {options}")
        options = options_window
    return options.get(key,default)

def setConfig(key, value, mid = None, windowName = None):
    userOption = getUserOption()
    options = userOption
    if mid is not None:
        mid = str(mid)
        if "mids" not in options:
            options["mids"] = dict()
        options = options["mids"]
        if mid not in options:
            options[mid] = dict()
        options = options[mid]
    if windowName is not None and not getConfig("same config for each window",True):
        if windowName not in options:
            options[windowName] = dict()
        options = options[windowName]
    options[key] = value
    mw.addonManager.writeConfig(__name__,userOption)


def update(_):
    global userOption
    userOption = None

mw.addonManager.setConfigUpdatedAction(__name__,update)
