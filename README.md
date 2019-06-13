# Milchior's Forked Anki

This is a forked version of Anki.

For official Anki, please see https://apps.ankiweb.net. To see the
difference between this fork and anki, see [difference.md](difference.md).

To run from source, please see README.development.

## Main idea

This forked Anki will include by default many useful add-ons which
does not fundamentally change the way anki is used. This would
hopefully allows users to install all those add-ons simultaneously,
instead of having to read the descriptions of each add-on, and take a
lot of time to decide which add-on to try.

This fork should, as much as possible, remains compatible with most
anki add-ons, in order to keep a single anki community. However, if an
add-on is incorporated in this fork, it won't be loaded by anki.

## Developpment process
### Branches
There are three kinds of branches used for this developpment.

#### Forked

This branch contains anki with every merged add-ons. This is probably
what you want to use, when using anki.

#### Add-on branch
Each add-on `A` correspond to a branch. This branch is, in theory, similar
to Anki's actualy code, with the difference that the add-on `A` is
merged to it, and its configuration is done in the Preferences.

This way, if some update of anki conflicts with Fork, it allows to
easily determines with which add-on it conflicts.

A copy of the add-on, at the time where it was incorporated, is also
added in this branch.

#### baseFork
This branch is identical to anki for the user. It contains everything
that will be used by Add-On branches, without actually containing
those add-ons. This branch is based on Arthur-Milchior's master
branch, which is a commented version of anki's code.

### Difference with anki's main branch
In this section, I list the difference between this fork and anki's
main branch.

#### Add-on folder
The folder addons contains the set of add-on which has been
incorporated in anki.

#### addons.py file
This file contains the set of add-ons incorporated with anki. Each
add-on have potentially a number, a name, a git hash, and a mod
value. This allows to ensure that if this add-on is in anki's add-on
folder, the add-on is not actually executed.

#### preferences
The preferences widges has an extra page. This page allows to
configure which add-ons are used and which add-ons are not used. It
also allow to configure the add-ons, similarly to the incorporated
add-on's configuration.
