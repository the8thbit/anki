# Differences with anki.
This files list the difference between regular anki and this forked
version. It also lists the different options in the Preferences's extra page.

## Added today (861864770)
From the add window page, you can see the list of cardes added today
in the browser.

## Add/remove deck prefix (683170394)
In the browser, you can select cards, and then do `Decks > Add
prefix`, to add the same prefix to the deck name of all of those
cards. This ensure that they all belong to a same deck, while keeping
the same deck hierarchy. `Decks > Remove prefix` allows to remove this
common prefix and thus cancel the action `Add prefix`.

## Batch Edit (291119185)
Allow to make the same edit to multiple cards. Either changing a
field, or adding text after/before it.

In preferences, you can decide whether you add a new line between the
old text and the added one.

## Changing a note type without synchronizing (719871418)
The preference "Change model without requiring a full sync" allow you
to avoid full sync after adding/removing a field or a card type to a
note type. However, this is risky. Thus you should only do this if you
are sure that the change on all devices are already
synchronized. Otherwise, it could create a bug.

## Copy note (1566928056)
If you select notes in the browser, and do `Notes>Copy Notes` or
`Ctrl+Alt+C`, a copy of the notes are created.

You have two options in the preferences:
* "Preserve date of creation": keeps the «Created» value in the
  browser. It is particularly interesting if you review cards
  according to their creation date.
* "Preserve easyness, interval, due date, ...": this create a copy of
  each card, as close as possible to the original card. If you uncheck
  this, instead, your new cards will be fresh, and you'll start review
  from 0.

## Correcting due (127334978)
Anki precomputes the order of the new cards to see. While in theory,
this is all nice, in practice it bugs in some strange case. Those
cases may occur in particular if you download a shared deck having
this bug. If you want details, it is explained here
https://github.com/Arthur-Milchior/anki/blob/master/documentation/due.md

Otherwise, you don't need to care about this change, except may be if
you use an add-on which itself change the order of card, such as the
«Hoochie»'s add-ons.

In the preferences, the button «Note with no card: create card 1
instead of deleting the note» chage the behavior of anki when he finds
a note which has no more card. This allow to lose the content of the
note, and let you correct the note instead to generate cards.

## Explain errors
You obtain more detailled error message if a sync fail, and if you try
do do a «Check database».

It transform the very long method `fixIntegrity` into plenty of small
function. It would helps to do add-ons for this forked version of anki.

## Usable card report (25425599)
Add more informations in the «empty card» report.

## When changing note type, preserve names (513858554)
If you change a note's type, and the old and the new note have
fields/cards with the same name, then those fields/cards are mapped by
default such that they keep the same name.

In preferences, you can unbox "When changing note type, preserve names
if possible." to recover anki's default behavior, i.e. sending first
element to first one, second to second, etc..
