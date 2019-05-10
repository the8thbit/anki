# Global process
## Main
Synchronization is done from ```aqt.main.AnkiQt._sync```. It creates a
SyncManager and asks it to sync.

## SyncManager
The function ```aqt.sync.SyncManager.sync``` checks whether it has the key. Otherwise
ask for it. The remaining is delegated to ```aqt.sync.SyncManager._sync```

The method ```_sync``` beging by creating a ```aqt.sync.SyncThread```
object and stating that each event is dealt with the method
```aqt.sync.SyncManager.onEvent```. It then starts the thread and
ensure that

While the tread runs, it checks 10 times by second:
* if the sync was cancelled, it display "stopping".
* it process the events.

Finally, if the thread has a syncMsg, show it. syncMsg being a message
that the server sent,

# Events
Here are the possible event which may occur
## newKey
This event arrive with an argument, probably a random string. It
should be sent during the successive synchronization.

This key can be used in place of the password. So the password does
not have to be saved on the computer. (Note that this key allows to do
synchronization, so it allows to do almost as many things as the
password. But it does not allow to share objects).
