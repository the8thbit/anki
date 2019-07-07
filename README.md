# Forked Anki, Alpha version
-------------------------------------

This is the development branch of a forked version of Anki. For official Anki, please see [https://apps.ankiweb.net](https://apps.ankiweb.net).

## Description
This is a version of anki in which multiple add-ons are already incorporated. I only incorporated add-ons which add more options (such as Copy notes, batch edit, exporting from browser, postponing cards, increasing speed of some operations, keeping some long term back-up, giving the name of cards which will be deleted instead of their index... ) without changing fundamentally the way Anki works.

I believe that this is a good idea for many reasons. That you'll have plenty of features without having to read the list of add-ons. Furthermore, there is no more problem of incompatible add-ons, since the features of each add-ons can be merged in the same code. Furthermore, I can now easily let you edit the configuration of Anki from the profile window, instead of having to ask people to edit a json file to configure the add-on.

It should be fully compatible with anki's add-on. And if an add-on is already incorporated in it, it won't be loaded.

This is a very early release. For example, you need to start this version of Anki by downloading the code from git-hub and executing runanki. I'll deal later with creating archive to download, as Anki does. I'd gladly have alpha testers.

The list of differences between Forked version and Anki is in https://github.com/Arthur-Milchior/anki/blob/fork/difference.md

## Notes for devs:
Honestly, I find that incorporating code in Anki is far easier than add-ons. Because:

I often need to monkey path a method by copying anki's method, adding it in an add-on, and changing a single line. which means that when this method change in Anki, my add-on won't change and will still have the old version. This lead to unexpected, hard to find bugs, which only appears when Anki is updated to a newer version. Using a fork, and merging regularly Anki with the forked version, this kind of problem will disappear.

There is no problem of add-on compatibility. Indeed, if many add-on change the same method, I can just do all the change in one file, instead of having to find arcane way to merge them. Currently, in add-ons, my answer is to do yet another add-on, merging the many incompatible add-ons. This is what I did, for example, when I created an add-on merging «multiple column editor» and «frozen fields», which is not a beautiful solution.

Some methods are extremely long, such as ``fixintegrity`` (i.e. "Check database"). I can now split this method in many smaller methods.

I can use anki's preference window to configure everything, instead of having to relies on json files, or in creating a specialized configuration window.

In order to be as compatible as possible with Anki, I respected the following rules. And I'll ensure that any pull request (if by luck, anyone is interested in contributing), satisfies the same rules:

all methods returns the same kind of values in the forked version and in Anki. So that any add-on calling those methods will have the expected result.

all methods takes the same arguments. Any other arguments are keyword argument. Most of the time, the default value could either ensure that Anki is imitated, unless there is a good reason not to do it.

the file aqt/addons.py contains the list of add-ons incorporated in Forked. So that those add-ons are not loaded. It also contains the git-hub repo, hash of the commit, and "mod" of the add-ons. So that I can be warned if an add-on is updated; and see whether I need to update Forked's code.

The folder addons/ contains a copy of the add-on, as it was when I incorporated it in Forked. So, if the add-on is updated, I can compare the previous version of the code, and the current version of the code.

The database is not changed at all. Because otherwise, it creates risk of incompatibility with ankidroid, ios and ankiweb. However, I allow to add element in json's dictionaries.



Here is what my different git branches are, and the way I intend to develop more features:

intToConstant: same as Anki, but some integers are replaced by constant (i.e. variable). This make the code easier to read without changing it. I would love this to be incorporated into anki's main code, but Damien was note interested (and anyway, it's not ready yet, because I use f-string, and he can't use f-string)

Commented: Same code as Anki, containing all changes from intToConstant, and containing a lot of comments. Some of you may already know this branch, since many people liked or forked my repo. This should help add-on developpers to understand Anki. It also contains documentation of many feature of Anki, which I shared with you on reddit in the past.

baseFork: this branch contains everything done in Commented, plus everything needed by the fork. I.e. an Add-on class, documentation about how to add feature to Forked, etc...However, it contains no add-ons, thus it should behave as Anki.

nameOfAnAddOn: there are plenty of branches of this kind. Each branch add a single feature to baseFork. This allow to test this feature alone. It also means that each time me (or another dev) want to add a feature, he can directly does it in a code looking like anki's code.

fork: this branch merges all branches of the previous kind. I.e. it
contains all features. Most merge are easy to do, except when two
merges change the same method. However, merges are never totally
trivial, because each feature adds elements to some list, and git
needs help in order to know in which order to keep each element in the
list. For the sake of simplicity, I keep them in alphabetical order as
much as I can.


To see the
difference between this fork and Anki, see [difference.md](difference.md).

For non-developers who want to try this development code,
the easiest way is to use a binary package - please see
https://anki.tenderapp.com/discussions/beta-testing

To run from source, please see README.development.

If you are interested in contributing changes to Anki, please
see README.contributing before you begin work.

[![Build Status](https://travis-ci.org/dae/anki.svg?branch=master)](https://travis-ci.org/dae/anki)
