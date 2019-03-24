In this file, I present anki's synchronization process. I first
describe the general mechanism used in anki's code (desktop
version). I then describe each step.

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

# Steps
## HostKey
The hostKey is an identifier given by the server which replace the
pair login/password. It is saved by anki when you sync. If you don't
have an hkey, anki asks to your login/password, and begin by sending a
request for an hostKey.

The post request `hostkey` request contains no post variable. Its
objects is the dictionnary with:
* 'u': the user login
* 'p': the password.

It return the hostkey.


## Meta
The post method `meta` request contains has post variable:
* 'k': the hkey,
* 's': a random string of 8 chars
it contains as object the dictionnary:
* 'v': SYNC_VER (currently 9, but I assume it may change when anki
  version change)
* 'cv': "ankidesktop,{versionWithBuild},{}"

It should return a dict containing:
* msg: An arbitrary message to show to the user at the end of the
  sync. Usually the empty string.
* cont: if its falsy, it means the server abort.
* scm: a schema modification time. If it's not equal to the
  collection's scm value, it mean that some part of the collection was
  modified (note type, card type) since last sync, and thus full
  update is required.
* ts: time stamp. The time according to the server. If the difference
  in time between server and computer is greater than 5 minutes, the
  synchronization is rejected. (Time zone are of cours taken into
  account)
* mod: the time of the last modification on the server. If it's value
  is equal to mod on the computer, it means that no change did occur,
  thus sync is not required.
* usn: Unique synchronization number. The greater usn of some anki
  object on the server is usn. Thus, the next modification will have
  synchronization number usn+1, to emphasize the state that it occurs
  after this synchronization.
* uname: (equivalent to syncName in the profile). The user name (i.e. login/email). It must be sent because the user
  may have chaged it on the server.
* hostnum: as in the profile. Its a value indicating which url/server to
  use for synchronization with anki.

## Basic check
The database will check that everything is consistent before
resuming. This is the first time it will occur. This check is
described in [BD_Check.md].

Hook ("sync","meta") is now called, but seems to have absolutly no
effect.
## Start
The post method ```start``` is sent with object a dictionnary:
* 'minUsn': the collection's value USN. I.e. the last number sent by
  the server (plus one). It represents the minimal USN of change that
  need to be downloaded.
* 'lnewer': whether collections's mod is greater than server's mod.

It return a dictionnary associating to each key a list of ids of
things to delete. Keys are notes, cards and decks. The content of the
deleted deck is not deleted, nor are the children of the deck if it
has any.

## applyGraves
The post method ```start``` is sent with object a dictionnary with a
unique key 'changes' whose value is a dict with keys "notes", "cards",
and "decks", each containing ids of object deleted since last
synchronization. At most 250 are sent, the command may be sent
multiple time if required.

## applyChanges
The post method ```start``` is sent with object a dictionnary with a
unique entry "changes", whose value is a dict with keys 'models',
'decks', 'tags' as they are saved as dict in the database. If mod is
newer here than on server, then the dict in the dict also contains key
'conf' and 'crt'.

It returns a dictionnary with:
* models: container of model (note type) dictionnary.
* decks: a list of two elements
** the decks, as in the case of models
** the dconf (deck options). As in the case of models.
* 'tags': the container of tags added.
* 'conf': (not mandatory. Probably only here if it did indeed changed)
* 'crt': as conf.

In each case, it sends only thing which changed, which may have to be
replaced in the collection. It is possible that the replacement does
not occur if the model have also been modified in the collection and
that the time of this modification is after the time of the
modification saved on the server.

## chunk
The post method ```chunk``` does not send anything. It receive a
dictionnary (the chunks) containing some keys in  'revlog', 'cards'
and 'notes', containing lines to enter in the table of database with
the same name (unless an entry with the same id is already here).

It also contains `done`, stating whether there are no more thing to download.

This post method is repeated until chunk['done'] is truthy. Each time,
hook ("sync","server") is called. But seems to have absolutly no effect.

## stream
The post method ```applyChunk``` takes as input a dictionnary, similar
to the one receveide by the ```chunk``` method. I.e. containing
keys `revlog`, `cards`, `notes` and `done`. This dic contains at most
250 elements.

This post method is repeated until there are no more new lines to
sent. Each time, hook ("sync","server") is called. But seems to have
absolutly no effect.

## sanityCheck

Hook ("sync","sanity") is called. It changes the message to
"Checking...".

It calls basic check and then ensures that USN should not be -1 in
cards, notes, revlog, graves, deck, tag, model. If it is the case,
return a string giving the name of the table not satisfying it.

If a non-root deck has no parent, it is created.


It computes the list ```c```
* three numbers to show in anki
* list/footer. I.e. Number of new cards, learning repetition,
* review card. (for selected deck),
* number of card,
* number of notes,
* number of revlog,
* number of grave,
* number of models,
* number of decks,
* number of deck's options.

## sanityCheck2
The method ```sanityCheck2``` is now called. It sends as objects
result ```c``` from sanityCheck. It returns a dictionnary ```dic```
which contains a key 'status'. Two paths are then taken, depending on
whether ```dic['sync']``` is the string 'ok' or not.

I assume taht ```ok``` occurs if the server, doing the same
computation, finds the same result. If so, it is possible that a sync
fail if it is done almost at time of new day, since the number of card
to review would be distinct on server and on computer.

### Finish (If it's 'ok')
runHook("sync", "finalize") is called. It does nothing.

The method ```finish``` does not sent any object. It returns a number,
which will become collections's ```ls``` value.

Collection _usn value is incremented to be maxUsn+1.

Database is considered to be modified. And then collection is saved.

### If it's anything but 'ok'
