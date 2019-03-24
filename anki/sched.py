# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import time
import random
import itertools
from operator import itemgetter
from heapq import *

#from anki.cards import Card
from anki.utils import ids2str, intTime, fmtTimeSpan
from anki.lang import _
from anki.consts import *
from anki.hooks import runHook

# queue types: 0=new/cram, 1=lrn, 2=rev, 3=day lrn, -1=suspended, -2=buried
# revlog types: 0=lrn, 1=rev, 2=relrn, 3=cram
# positive revlog intervals are in days (rev), negative in seconds (lrn)

class Scheduler:
    """
    today -- difference between the last time scheduler is seen and creation of the collection.
    dayCutoff -- The timestamp of when today end.
    reportLimit -- the maximal number to show in main windows
    lrnCount --  The number of cards in learning in selected decks
    revCount -- number of cards to review today in selected decks
    newCount -- number of new cards to see today in selected decks
    _lrnDids, _revDids, _newDids -- a copy of the set of active decks
    _newQueue, _lrnQueue, _revQueue -- todo
    _lrnDayQueue -- todo
    newCardModulus -- each card in position 0 Modulo newCardModulus is a new card. Or it is 0 if new cards are not mixed with reviews.
    -- _haveQueues -- whether the number of cards to see today for current decks have been set.
    """
    name = "std"
    haveCustomStudy = True
    _spreadRev = True
    _burySiblingsOnAnswer = True

    def __init__(self, col):
        self.col = col
        self.queueLimit = 50
        self.reportLimit = 1000
        self.reps = 0
        self.today = None
        self._haveQueues = False
        self._updateCutoff()

    def getCard(self):
        "Pop the next card from the queue. None if finished."
        self._checkDay()
        if not self._haveQueues:
            self.reset()
        card = self._getCard()
        if card:
            self.col.log(card)
            if not self._burySiblingsOnAnswer:
                self._burySiblings(card)
            self.reps += 1
            card.startTimer()
            return card

    def reset(self):
        """
        Deal with the fact that it's potentially a new day.
        Reset number of learning, review, new cards according to current decks
        empty queues. Set haveQueues to true
        """
        self._updateCutoff()
        self._resetLrn()
        self._resetRev()
        self._resetNew()
        self._haveQueues = True

    def answerCard(self, card, ease):
        """Change the number of card to see in the decks and its
        ancestors. Change the due/interval/ease factor of this card,
        according to the button ease.

        """
        self.col.log()
        assert 1 <= ease <= 4
        self.col.markReview(card)
        if self._burySiblingsOnAnswer:
            self._burySiblings(card)
        card.reps += 1
        # former is for logging new cards, latter also covers filt. decks
        card.wasNew = card.type == CARD_NEW
        wasNewQ = card.queue == QUEUE_NEW_CRAM
        if wasNewQ:
            # came from the new queue, move to learning
            card.queue = QUEUE_LRN
            # if it was a new card, it's now a learning card
            if card.type == CARD_NEW:
                card.type = CARD_LRN
            # init reps to graduation
            card.left = self._startingLeft(card)
            # dynamic?
            if card.odid and card.type == CARD_DUE:
                if self._resched(card):
                    # reviews get their ivl boosted on first sight
                    card.ivl = self._dynIvlBoost(card)
                    card.odue = self.today + card.ivl
            self._updateStats(card, 'new')
        if card.queue in (QUEUE_LRN, QUEUE_DAY_LRN):
            self._answerLrnCard(card, ease)
            if not wasNewQ:# if wasNewQ holds, updating already
                # happened above
                self._updateStats(card, 'lrn')
        elif card.queue == QUEUE_REV:
            self._answerRevCard(card, ease)
            self._updateStats(card, 'rev')
        else:
            raise Exception(f"Invalid queue")
        self._updateStats(card, 'time', card.timeTaken())
        card.mod = intTime()
        card.usn = self.col.usn()
        card.flushSched()

    def counts(self, card=None):
        """The three numbers to show in anki deck's list/footer.
        Number of new cards, learning repetition, review card.

        If cards, then the tuple takes into account the card.
"""
        counts = [self.newCount, self.lrnCount, self.revCount]
        if card:
            idx = self.countIdx(card)
            if idx == QUEUE_LRN:
                counts[1] += card.left // 1000
            else:
                counts[idx] += 1
        return tuple(counts)

    def dueForecast(self, days=7):
        "Return counts over next DAYS. Includes today."
        daysd = dict(self.col.db.all(f"""
select due, count() from cards
where did in %s and queue = {QUEUE_REV}
and due between ? and ?
group by due
order by due""" % (self._deckLimit()),
                            self.today,
                            self.today+days-1))
        for d in range(days):
            d = self.today+d
            if d not in daysd:
                daysd[d] = 0
        # return in sorted order
        ret = [x[1] for x in sorted(daysd.items())]
        return ret

    def countIdx(self, card):
        """In which column the card in the queue should be counted.
        day_lrn is sent to lrn, otherwise its the identity"""
        if card.queue == QUEUE_DAY_LRN:
            return QUEUE_LRN
        return card.queue

    def answerButtons(self, card):
        if card.odue:
            # normal review in dyn deck?
            if card.odid and card.queue == QUEUE_REV:
                return BUTTON_FOUR
            conf = self._lrnConf(card)
            if card.type in (CARD_NEW,CARD_LRN) or len(conf['delays']) > 1:
                return BUTTON_THREE
            return BUTTON_TWO
        elif card.queue == QUEUE_REV:
            return BUTTON_FOUR
        else:
            return BUTTON_THREE

    def unburyCards(self):
        "Unbury cards."
        self.col.conf['lastUnburied'] = self.today
        self.col.log(
            self.col.db.list(f"select id from cards where queue = {QUEUE_USER_BURIED}"))
        self.col.db.execute(
            f"update cards set queue=type where queue = {QUEUE_USER_BURIED}")

    def unburyCardsForDeck(self):
        sids = ids2str(self.col.decks.active())
        self.col.log(
            self.col.db.list(f"select id from cards where queue = {QUEUE_USER_BURIED} and did in %s"
                             % (sids)))
        self.col.db.execute(
            f"update cards set mod=?,usn=?,queue=type where queue = {QUEUE_USER_BURIED} and did in %s"
            % (sids), intTime(), self.col.usn())

    # Rev/lrn/time daily stats
    ##########################################################################

    def _updateStats(self, card, type, cnt=1):
        """Change the number of review/new/learn cards to see today in card's
        deck, and in all of its ancestors. The number of card to see
        is decreased by cnt.

        if type is time, it adds instead the time taken in this card
        to this decks and all of its ancestors.
        """
        key = type+"Today"
        for g in ([self.col.decks.get(card.did)] +
                  self.col.decks.parents(card.did)):
            # add
            g[key][1] += cnt
            self.col.decks.save(g)

    def extendLimits(self, new, rev):
        cur = self.col.decks.current()
        parents = self.col.decks.parents(cur['id'])
        children = [self.col.decks.get(did) for (name, did) in
                    self.col.decks.children(cur['id'])]
        for g in [cur] + parents + children:
            # add
            g['newToday'][1] -= new
            g['revToday'][1] -= rev
            self.col.decks.save(g)

    def _walkingCount(self, limFn=None, cntFn=None):
        """The sum of cntFn applied to each active deck.

        Taking into account the limit computed by limFn"""
        tot = 0
        pcounts = {}
        # for each of the active decks
        nameMap = self.col.decks.nameMap()
        for did in self.col.decks.active():
            # early alphas were setting the active ids as a str
            did = int(did)
            # get the individual deck's limit
            lim = limFn(self.col.decks.get(did))
            if not lim:
                continue
            # check the parents
            parents = self.col.decks.parents(did, nameMap)
            for p in parents:
                # add if missing
                if p['id'] not in pcounts:
                    pcounts[p['id']] = limFn(p)
                # take minimum of child and parent
                lim = min(pcounts[p['id']], lim)
            # see how many cards we actually have
            cnt = cntFn(did, lim)
            # if non-zero, decrement from parent counts
            for p in parents:
                pcounts[p['id']] -= cnt
            # we may also be a parent
            pcounts[did] = lim - cnt
            # and add to running total
            tot += cnt
        return tot

    # Deck list
    ##########################################################################

    def deckDueList(self):
        """
        Similar to nodes, without the recursive counting, with the full deck name

        [deckname (with ::),
        did, rev, lrn, new (not counting subdeck)]"""
        self._checkDay()
        self.col.decks.checkIntegrity()
        decks = self.col.decks.all()
        decks.sort(key=itemgetter('name'))
        #lims -- associating to each deck maximum number of new card and of review. Taking custom study into account
        lims = {}
        data = []
        def parent(name):
            parts = name.split("::")
            if len(parts) < 2:
                return None
            parts = parts[:-1]
            return "::".join(parts)
        for deck in decks:
            p = parent(deck['name'])
            # new
            #nlim -- maximal number of new card, taking parent into account
            nlim = self._deckNewLimitSingle(deck)
            if p:
                nlim = min(nlim, lims[p][0])
            new = self._newForDeck(deck['id'], nlim)
            # learning
            lrn = self._lrnForDeck(deck['id'])
            # reviews
            #rlim -- maximal number of review, taking parent into account
            rlim = self._deckRevLimitSingle(deck)
            if p:
                rlim = min(rlim, lims[p][1])
            rev = self._revForDeck(deck['id'], rlim)
            # save to list
            data.append([deck['name'], deck['id'], rev, lrn, new])
            # add deck as a parent
            lims[deck['name']] = [nlim, rlim]
        return data

    def deckDueTree(self):
        """Generate the node of the main deck. See deckbroser introduction to see what a node is
        """
        #something similar to nodes, but without the recursive part
        nodes_=self.deckDueList()
        #the actual nodes
        nodes=self._groupChildren(nodes_)
        return nodes

    def _groupChildren(self, grps):
        """[subdeck name without parent parts,
        did, rev, lrn, new (counting subdecks)
        [recursively the same things for the children]]

        Keyword arguments:
        grps -- [deckname, did, rev, lrn, new]
        """
        # first, split the group names into components
        for g in grps:
            g[0] = g[0].split("::")
        # and sort based on those components
        grps.sort(key=itemgetter(0))
        # then run main function
        return self._groupChildrenMain(grps)

    def _groupChildrenMain(self, grps):
        """
        [subdeck name without parent parts,
        did, rev, lrn, new (counting subdecks)
        [recursively the same things for the children]]

        keyword arguments:
        grps -- [[subdeck], did, rev, lrn, new] sorted according to the list subdeck. Number for the subdeck precisely"""
        tree = []
        # group and recurse
        def key(grp):
            return grp[0][0]
        for (head, tail) in itertools.groupby(grps, key=key):
            tail = list(tail)
            did = None
            rev = 0
            new = 0
            lrn = 0
            children = []
            for c in tail:
                if len(c[0]) == 1:
                    # current node
                    did = c[1]
                    rev += c[2]
                    lrn += c[3]
                    new += c[4]
                else:
                    # set new string to tail
                    c[0] = c[0][1:]
                    children.append(c)
            children = self._groupChildrenMain(children)
            # tally up children counts
            for ch in children:
                rev += ch[2]
                lrn += ch[3]
                new += ch[4]
            # limit the counts to the deck's limits
            conf = self.col.decks.confForDid(did)
            deck = self.col.decks.get(did)
            if not conf['dyn']:
                rev = max(0, min(rev, conf['rev']['perDay']-deck['revToday'][1]))
                new = max(0, min(new, conf['new']['perDay']-deck['newToday'][1]))
            tree.append((head, did, rev, lrn, new, children))
        return tuple(tree)

    # Getting the next card
    ##########################################################################

    def _getCard(self):
        "Return the next due card id, or None."
        # learning card due?
        c = self._getLrnCard()
        if c:
            return c
        # new first, or time for one?
        if self._timeForNewCard():
            c = self._getNewCard()
            if c:
                return c
        # card due for review?
        c = self._getRevCard()
        if c:
            return c
        # day learning card due?
        c = self._getLrnDayCard()
        if c:
            return c
        # new cards left?
        c = self._getNewCard()
        if c:
            return c
        # collapse or finish
        return self._getLrnCard(collapse=True)

    # New cards
    ##########################################################################

    def _resetNewCount(self):
        """Set newCount to the counter of new cards for the active decks"""
        cntFn = lambda did, lim: self.col.db.scalar(f"""
select count() from (select 1 from cards where
did = ? and queue = {QUEUE_NEW_CRAM} limit ?)""", did, lim)
        self.newCount = self._walkingCount(self._deckNewLimitSingle, cntFn)

    def _resetNew(self):
        """Set newCount, newDids, newCardModulus. Empty newQueue. """
        self._resetNewCount()
        self._newDids = self.col.decks.active()[:]
        self._newQueue = []
        self._updateNewCardRatio()

    def _fillNew(self):
        if self._newQueue:
            return True
        if not self.newCount:
            return False
        while self._newDids:
            did = self._newDids[0]
            lim = min(self.queueLimit, self._deckNewLimit(did))
            if lim:
                # fill the queue with the current did
                self._newQueue = self.col.db.list(f"""
                select id from cards where did = ? and queue = {QUEUE_NEW_CRAM} order by due,ord limit ?""" , did, lim)
                if self._newQueue:
                    self._newQueue.reverse()
                    return True
            # nothing left in the deck; move to next
            self._newDids.pop(0)
        if self.newCount:
            # if we didn't get a card but the count is non-zero,
            # we need to check again for any cards that were
            # removed from the queue but not buried
            self._resetNew()
            return self._fillNew()

    def _getNewCard(self):
        if self._fillNew():
            self.newCount -= 1
            return self.col.getCard(self._newQueue.pop())

    def _updateNewCardRatio(self):
        """set newCardModulus so that new cards are regularly mixed with review cards. At least 2.
        Only if new and review should be mixed"""
        if self.col.conf['newSpread'] == NEW_CARDS_DISTRIBUTE:
            if self.newCount:
                self.newCardModulus = (
                    (self.newCount + self.revCount) // self.newCount)
                # if there are cards to review, ensure modulo >= 2
                if self.revCount:
                    self.newCardModulus = max(2, self.newCardModulus)
                return
        self.newCardModulus = 0

    def _timeForNewCard(self):
        "True if it's time to display a new card when distributing."
        if not self.newCount:
            return False
        if self.col.conf['newSpread'] == NEW_CARDS_LAST:
            return False
        elif self.col.conf['newSpread'] == NEW_CARDS_FIRST:
            return True
        elif self.newCardModulus:
            return self.reps and self.reps % self.newCardModulus == 0

    def _deckNewLimit(self, did, fn=None):
        if not fn:
            fn = self._deckNewLimitSingle
        sel = self.col.decks.get(did)
        lim = -1
        # for the deck and each of its parents
        for g in [sel] + self.col.decks.parents(did):
            rem = fn(g)
            if lim == -1:
                lim = rem
            else:
                lim = min(rem, lim)
        return lim

    def _newForDeck(self, did, lim):
        """The minimum between the number of new cards in this deck lim and self.reportLimit.

        keyword arguments:
        did -- id of a deck
        lim -- an upper bound for the returned number (in practice, the number of new cards to see by day for the deck's option) """
        if not lim:
            return 0
        lim = min(lim, self.reportLimit)
        return self.col.db.scalar(f"""
select count() from
(select 1 from cards where did = ? and queue = {QUEUE_NEW_CRAM} limit ?)""", did, lim)

    def _deckNewLimitSingle(self, g):
        "Limit for deck without parent limits."
        if g['dyn']:
            return self.reportLimit
        c = self.col.decks.confForDid(g['id'])
        return max(0, c['new']['perDay'] - g['newToday'][1])

    def totalNewForCurrentDeck(self):
        return self.col.db.scalar(
            f"""
select count() from cards where id in (
select id from cards where did in %s and queue = {QUEUE_NEW_CRAM} limit ?)"""
            % (ids2str(self.col.decks.active()), self.reportLimit))

    # Learning queues
    ##########################################################################

    def _resetLrnCount(self):
        """Set lrnCount"""
        # Number of reps which are due today, last seen today caped by report limit, in the selected decks
        self.lrnCount = self.col.db.scalar(f"""
select sum(left/1000) from (select left from cards where
did in %s and queue = {QUEUE_LRN} and due < ? limit %d)""" % (
            self._deckLimit(), self.reportLimit),
            self.dayCutoff) or 0
        # Number of cards in learning which are due today, last seen another day caped by report limit, in the selected decks
        self.lrnCount += self.col.db.scalar(f"""
select count() from cards where did in %s and queue = {QUEUE_DAY_LRN}
and due <= ? limit %d""" % (self._deckLimit(),  self.reportLimit),
                                            self.today)

    def _resetLrn(self):
        """Set lrnCount and _lrnDids. Empty _lrnQueue, lrnDayQueu."""
        self._resetLrnCount()
        self._lrnQueue = []
        self._lrnDayQueue = []
        self._lrnDids = self.col.decks.active()[:]

    # sub-day learning
    def _fillLrn(self):
        if not self.lrnCount:
            return False
        if self._lrnQueue:
            return True
        self._lrnQueue = self.col.db.all(f"""
select due, id from cards where
did in %s and queue = {QUEUE_LRN} and due < :lim
limit %d""" % (self._deckLimit(), self.reportLimit), lim=self.dayCutoff)
        # as it arrives sorted by did first, we need to sort it
        self._lrnQueue.sort()
        return self._lrnQueue

    def _getLrnCard(self, collapse=False):
        if self._fillLrn():
            cutoff = time.time()
            if collapse:
                cutoff += self.col.conf['collapseTime']
            if self._lrnQueue[0][0] < cutoff:
                id = heappop(self._lrnQueue)[1]
                card = self.col.getCard(id)
                self.lrnCount -= card.left // 1000
                return card

    # daily learning
    def _fillLrnDay(self):
        if not self.lrnCount:
            return False
        if self._lrnDayQueue:
            return True
        while self._lrnDids:
            did = self._lrnDids[0]
            # fill the queue with the current did
            self._lrnDayQueue = self.col.db.list(f"""
select id from cards where
did = ? and queue = {QUEUE_DAY_LRN} and due <= ? limit ?""",
                                    did, self.today, self.queueLimit)
            if self._lrnDayQueue:
                # order
                r = random.Random()
                r.seed(self.today)
                r.shuffle(self._lrnDayQueue)
                # is the current did empty?
                if len(self._lrnDayQueue) < self.queueLimit:
                    self._lrnDids.pop(0)
                return True
            # nothing left in the deck; move to next
            self._lrnDids.pop(0)

    def _getLrnDayCard(self):
        if self._fillLrnDay():
            self.lrnCount -= 1
            return self.col.getCard(self._lrnDayQueue.pop())

    def _answerLrnCard(self, card, ease):
        # ease 1=no, 2=yes, 3=remove
        conf = self._lrnConf(card)
        if card.odid and not card.wasNew:
            type = REVLOG_CRAM
        elif card.type == CARD_DUE:
            type = REVLOG_RELRN
        else:
            type = REVLOG_LRN
        leaving = False
        # lrnCount was decremented once when card was fetched
        lastLeft = card.left
        # immediate graduate?
        if ease == BUTTON_THREE:
            self._rescheduleAsRev(card, conf, True)
            leaving = True
        # graduation time?
        elif ease == BUTTON_TWO and (card.left%1000)-1 <= 0:
            self._rescheduleAsRev(card, conf, False)
            leaving = True
        else:
            # one step towards graduation
            if ease == BUTTON_TWO:
                # decrement real left count and recalculate left today
                left = (card.left % 1000) - 1
                card.left = self._leftToday(conf['delays'], left)*1000 + left
            # failed
            else:
                card.left = self._startingLeft(card)
                resched = self._resched(card)
                if 'mult' in conf and resched:
                    # review that's lapsed
                    card.ivl = max(1, conf['minInt'], card.ivl*conf['mult'])
                else:
                    # new card; no ivl adjustment
                    pass
                if resched and card.odid:
                    card.odue = self.today + 1
            delay = self._delayForGrade(conf, card.left)
            if card.due < time.time():
                # not collapsed; add some randomness
                delay *= random.uniform(1, 1.25)
            card.due = int(time.time() + delay)
            # due today?
            if card.due < self.dayCutoff:
                self.lrnCount += card.left // 1000
                # if the queue is not empty and there's nothing else to do, make
                # sure we don't put it at the head of the queue and end up showing
                # it twice in a row
                card.queue = QUEUE_LRN
                if self._lrnQueue and not self.revCount and not self.newCount:
                    smallestDue = self._lrnQueue[0][0]
                    card.due = max(card.due, smallestDue+1)
                heappush(self._lrnQueue, (card.due, card.id))
            else:
                # the card is due in one or more days, so we need to use the
                # day learn queue
                ahead = ((card.due - self.dayCutoff) // 86400) + 1
                card.due = self.today + ahead
                card.queue = QUEUE_DAY_LRN
        self._logLrn(card, ease, conf, leaving, type, lastLeft)

    def _delayForGrade(self, conf, left):
        """The number of second for the delay until the next time the card can
        be reviewed. Assuming the number of left steps is left,
        according to configuration conf

        """
        left = left % 1000
        try:
            delay = conf['delays'][-left]
        except IndexError:
            if conf['delays']:
                delay = conf['delays'][0]
            else:
                # user deleted final step; use dummy value
                delay = 1
        return delay*60

    def _lrnConf(self, card):
        """ lapse configuration if the card was due(i.e. review card
        ?), otherwise new configuration.  I don't get the point"""
        if card.type == CARD_DUE:
            return self._lapseConf(card)
        else:
            return self._newConf(card)

    def _rescheduleAsRev(self, card, conf, early):
        """ Change schedule for graduation.

        If it's filtered without rescheduling, remove the card from
        filtered and do nothing else.

        If it's lapsed, set the due date to tomorrow. Do not change
        the interval.

        If it's a new card, change interval according to
        _rescheduleNew. I.e. conf['ints'][1 if early
        else 0]", change the due date accordingly. Change the easyness
        to initial one.
        """
        lapse = card.type == CARD_DUE
        if lapse:
            if self._resched(card):
                card.due = max(self.today+1, card.odue)
            else:
                card.due = card.odue
            card.odue = 0
        else:
            self._rescheduleNew(card, conf, early)
        # Interval is now set. We must deal with queue and moving deck
        # if dynamic.
        card.queue = QUEUE_REV
        card.type = CARD_DUE
        # if we were dynamic, graduating means moving back to the old deck
        resched = self._resched(card)
        if card.odid:
            card.did = card.odid
            card.odue = 0
            card.odid = 0
            # if rescheduling is off, it needs to be set back to a new card
            if not resched and not lapse:
                card.queue = QUEUE_NEW_CRAM
                card.type = CARD_NEW
                card.due = self.col.nextID("pos")

    def _startingLeft(self, card):
        """(number of review to see, number which can be seen today)
        But instead of a pair (a,b), returns a+1000*b.
        """
        if card.type == CARD_DUE:
            conf = self._lapseConf(card)
        else:
            conf = self._lrnConf(card)
        tot = len(conf['delays'])
        tod = self._leftToday(conf['delays'], tot)
        return tot + tod*1000

    def _leftToday(self, delays, left, now=None):
        """The number of the last ```left``` steps that can be completed
        before the day cutoff. Assuming the first step is done
        ```now```.

        delays -- the list of delays
        left -- the number of step to consider (at the end of the
        list)
        now -- the time at which the first step is done.
        """
        if not now:
            now = intTime()
        delays = delays[-left:]
        ok = 0
        for i in range(len(delays)):
            now += delays[i]*60
            if now > self.dayCutoff:
                break
            ok = i
        return ok+1

    def _graduatingIvl(self, card, conf, early, adj=True):
        """
        The interval before the next review.
        If its lapsed card in a filtered deck, then use _dynIvlBoost.
        Otherwise, if button was easy or not, use the 'ints' value
        according to conf parameter.
        Maybe apply some fuzzyness according to adj

        Card is supposed to be in learning.
        card -- a card object
        conf -- the configuration dictionnary for this kind of card
        early -- whether "easy" was pressed
        adj -- whether to add fuzziness
        """
        if card.type == CARD_DUE:
            # lapsed card being relearnt
            if card.odid:
                if conf['resched']:
                    return self._dynIvlBoost(card)
            return card.ivl
        if not early:
            # graduate
            ideal =  conf['ints'][0]
        else:
            # early remove
            ideal = conf['ints'][1]
        if adj:
            return self._adjRevIvl(card, ideal)
        else:
            return ideal

    def _rescheduleNew(self, card, conf, early):
        """Reschedule a new card that's graduated for the first time.

        Set its factor according to conf.
        Set its interval. If it's lapsed in dynamic deck, use
        _dynIvlBoost.
        Otherwise, the interval is found in conf['ints'][1 if early
        else 0].
        Change due date according to the interval.
        Put initial factor.
        """
        card.ivl = self._graduatingIvl(card, conf, early)
        card.due = self.today+card.ivl
        card.factor = conf['initialFactor']

    def _logLrn(self, card, ease, conf, leaving, type, lastLeft):
        lastIvl = -(self._delayForGrade(conf, lastLeft))
        ivl = card.ivl if leaving else -(self._delayForGrade(conf, card.left))
        def log():
            self.col.db.execute(
                "insert into revlog values (?,?,?,?,?,?,?,?,?)",
                int(time.time()*1000), card.id, self.col.usn(), ease,
                ivl, lastIvl, card.factor, card.timeTaken(), type)
        try:
            log()
        except:
            # duplicate pk; retry in 10ms
            time.sleep(0.01)
            log()

    def removeLrn(self, ids=None):
        "Remove cards from the learning queues."
        if ids:
            extra = " and id in "+ids2str(ids)
        else:
            # benchmarks indicate it's about 10x faster to search all decks
            # with the index than scan the table
            extra = " and did in "+ids2str(self.col.decks.allIds())
        # review cards in relearning
        self.col.db.execute(f"""
update cards set
due = odue, queue = {QUEUE_REV}, mod = %d, usn = %d, odue = 0
where queue in ({QUEUE_LRN},{QUEUE_DAY_LRN}) and type = {CARD_DUE}
%s
""" % (intTime(), self.col.usn(), extra))
        # new cards in learning
        self.forgetCards(self.col.db.list(
            f"select id from cards where queue in ({QUEUE_LRN}, {QUEUE_DAY_LRN}) %s" % extra))

    def _lrnForDeck(self, did):
        """Number of review of cards in learing of deck did. """
        cnt = self.col.db.scalar(
            f"""
select sum(left/1000) from
(select left from cards where did = ? and queue = {QUEUE_LRN} and due < ? limit ?)""",
            did, intTime() + self.col.conf['collapseTime'], self.reportLimit) or 0
        return cnt + self.col.db.scalar(
            f"""
select count() from
(select 1 from cards where did = ? and queue = {QUEUE_DAY_LRN}
and due <= ? limit ?)""" ,
            did, self.today, self.reportLimit)

    # Reviews
    ##########################################################################

    def _deckRevLimit(self, did):
        return self._deckNewLimit(did, self._deckRevLimitSingle)

    def _deckRevLimitSingle(self, d):
        """The number of cards remaining to review today.

        Custom study taken into account """
        if d['dyn']:
            return self.reportLimit
        c = self.col.decks.confForDid(d['id'])
        return max(0, c['rev']['perDay'] - d['revToday'][1])

    def _revForDeck(self, did, lim):
        """number of cards to review today for deck did

        Minimum between this number, self report and limit. Not taking subdeck into account """
        lim = min(lim, self.reportLimit)
        return self.col.db.scalar(
            f"""
select count() from
(select 1 from cards where did = ? and queue = {QUEUE_REV}
and due <= ? limit ?)""",
            did, self.today, lim)

    def _resetRevCount(self):
        """Set revCount"""
        def cntFn(did, lim):
            """Number of review cards to see today"""
            return self.col.db.scalar(f"""
select count() from (select id from cards where
did = ? and queue = {QUEUE_REV} and due <= ? limit %d)""" % (lim),
                                      did, self.today)
        self.revCount = self._walkingCount(
            self._deckRevLimitSingle, cntFn)

    def _resetRev(self):
        """Set revCount, empty _revQueue, _revDids"""
        self._resetRevCount()
        self._revQueue = []
        self._revDids = self.col.decks.active()[:]

    def _fillRev(self):
        if self._revQueue:
            return True
        if not self.revCount:
            return False
        while self._revDids:
            did = self._revDids[0]
            lim = min(self.queueLimit, self._deckRevLimit(did))
            if lim:
                # fill the queue with the current did
                self._revQueue = self.col.db.list(f"""
select id from cards where
did = ? and queue = {QUEUE_REV} and due <= ? limit ?""",
                                                  did, self.today, lim)
                if self._revQueue:
                    # ordering
                    if self.col.decks.get(did)['dyn']:
                        # dynamic decks need due order preserved
                        self._revQueue.reverse()
                    else:
                        # random order for regular reviews
                        r = random.Random()
                        r.seed(self.today)
                        r.shuffle(self._revQueue)
                    # is the current did empty?
                    if len(self._revQueue) < lim:
                        self._revDids.pop(0)
                    return True
            # nothing left in the deck; move to next
            self._revDids.pop(0)
        if self.revCount:
            # if we didn't get a card but the count is non-zero,
            # we need to check again for any cards that were
            # removed from the queue but not buried
            self._resetRev()
            return self._fillRev()

    def _getRevCard(self):
        if self._fillRev():
            self.revCount -= 1
            return self.col.getCard(self._revQueue.pop())

    def totalRevForCurrentDeck(self):
        return self.col.db.scalar(
            """
select count() from cards where id in (
select id from cards where did in %s and queue = {QUEUE_REV} and due <= ? limit ?)"""
            % (ids2str(self.col.decks.active()), self.today, self.reportLimit))

    # Answering a review card
    ##########################################################################

    def _answerRevCard(self, card, ease):
        """
        move the card out of filtered if required
        change the queue

        if not (filtered without rescheduling):
        change interval
        change due
        change factor
        change lapse if BUTTON_ONE

        log this review
        """
        delay = 0
        if ease == BUTTON_ONE:
            delay = self._rescheduleLapse(card)
        else:
            self._rescheduleRev(card, ease)
        self._logRev(card, ease, delay)

    def _rescheduleLapse(self, card):
        """
        The number of second for the delay until the next time the card can
        be reviewed. 0 if it should not be reviewed (because leech, or
        because conf['delays'] is empty)

        Called the first time we press "again" on a review card.


        Unless filtered without reschedule:
        lapse incread
        ivl changed
        factor decreased by 200
        due changed.

        if leech, suspend and return 0.

        card -- review card
        """

        conf = self._lapseConf(card)
        card.lastIvl = card.ivl
        if self._resched(card):
            card.lapses += 1
            card.ivl = self._nextLapseIvl(card, conf)
            card.factor = max(1300, card.factor-200)
            card.due = self.today + card.ivl
            # if it's a filtered deck, update odue as well
            if card.odid:
                card.odue = card.due
        # if suspended as a leech, nothing to do
        delay = 0
        if self._checkLeech(card, conf) and card.queue == QUEUE_SUSPENDED:
            return delay#i.e. return 0
        # if no relearning steps, nothing to do
        if not conf['delays']:
            return delay#i.e. return 0
        # record rev due date for later
        if not card.odue:
            card.odue = card.due
        delay = self._delayForGrade(conf, 0)
        card.due = int(delay + time.time())
        #number of rev+1000*number of rev to do today
        card.left = self._startingLeft(card)
        # queue LRN
        if card.due < self.dayCutoff:
            self.lrnCount += card.left // 1000
            card.queue = QUEUE_LRN
            heappush(self._lrnQueue, (card.due, card.id))
        else:
            # day learn queue
            ahead = ((card.due - self.dayCutoff) // 86400) + 1
            card.due = self.today + ahead
            card.queue = QUEUE_DAY_LRN
        return delay

    def _nextLapseIvl(self, card, conf):
        return max(conf['minInt'], int(card.ivl*conf['mult']))

    def _rescheduleRev(self, card, ease):
        """Update the card according to review.

        If it's filtered, remove from filtered. If the filtered deck
        states not to update, nothing else is done.

        Change the interval. Change the due date. Change the factor.


        ease -- button pressed. Between 2 and 4
        card -- assumed to be in review mode

        """
        # update interval
        card.lastIvl = card.ivl
        if self._resched(card):
            self._updateRevIvl(card, ease)
            # then the rest
            card.factor = max(1300, card.factor+[-150, 0, 150][ease-2])
            card.due = self.today + card.ivl
        else:
            card.due = card.odue
        if card.odid:
            card.did = card.odid
            card.odid = 0
            card.odue = 0

    def _logRev(self, card, ease, delay):
        """Log this review. Retry once if failed"""
        def log():
            self.col.db.execute(
                "insert into revlog values (?,?,?,?,?,?,?,?,?)",
                int(time.time()*1000), card.id, self.col.usn(), ease,
                -delay or card.ivl, card.lastIvl, card.factor, card.timeTaken(),
                1)
        try:
            log()
        except:
            # duplicate pk; retry in 10ms
            time.sleep(0.01)
            log()

    # Interval management
    ##########################################################################

    def _nextRevIvl(self, card, ease):
        """Ideal next interval for CARD, given EASE.

        Fuzzyness not applied.
        Cardds assumed to be a review card succesfully reviewed."""
        delay = self._daysLate(card)
        conf = self._revConf(card)
        fct = card.factor / 1000
        ivl2 = self._constrainedIvl((card.ivl + delay // 4) * 1.2, conf, card.ivl)
        ivl3 = self._constrainedIvl((card.ivl + delay // 2) * fct, conf, ivl2)
        ivl4 = self._constrainedIvl(
            (card.ivl + delay) * fct * conf['ease4'], conf, ivl3)
        if ease == BUTTON_TWO:
            interval = ivl2
        elif ease == BUTTON_THREE:
            interval = ivl3
        elif ease == BUTTON_FOUR:
            interval = ivl4
        # interval capped?
        return min(interval, conf['maxIvl'])

    def _fuzzedIvl(self, ivl):
        """Return a randomly chosen number of day for the interval,
        not far from ivl.

        See ../documentation/computing_intervals for a clearer version
        of this documentation
        """
        min, max = self._fuzzIvlRange(ivl)
        return random.randint(min, max)

    def _fuzzIvlRange(self, ivl):
        """Return an increasing pair of numbers.  The new interval will be a
        number randomly selected between the first and the second
        element.

        See ../documentation/computing_intervals for a clearer version
        of this documentation

        """
        if ivl < 2:
            return [1, 1]
        elif ivl == 2:
            return [2, 3]
        elif ivl < 7:
            fuzz = int(ivl*0.25)
        elif ivl < 30:
            fuzz = max(2, int(ivl*0.15))
        else:
            fuzz = max(4, int(ivl*0.05))
        # fuzz at least a day
        fuzz = max(fuzz, 1)
        return [ivl-fuzz, ivl+fuzz]

    def _constrainedIvl(self, ivl, conf, prev):
        """A new interval. Ivl multiplie by the interval
        factor of this conf. Greater than prev.
        """
        new = ivl * conf.get('ivlFct', 1)
        return int(max(new, prev+1))

    def _daysLate(self, card):
        "Number of days later than scheduled."
        due = card.odue if card.odid else card.due
        return max(0, self.today - due)

    def _updateRevIvl(self, card, ease):
        """ Compute the next interval, fuzzy it, ensure ivl increase
        and is at most maxIvl.

        Card is assumed to be a review card."""
        idealIvl = self._nextRevIvl(card, ease)
        fuzzedIvl = self._adjRevIvl(card, idealIvl)
        increasedIvl = max(fuzzedIvl, card.ivl+1)
        card.ivl = min(increasedIvl, self._revConf(card)['maxIvl'])

    def _adjRevIvl(self, card, idealIvl):
        """Return an interval, similar to idealIvl, but randomized.
        See ../documentation/computing_intervals for the rule to
        generate this fuzziness.

        if _speadRev is to False (by an Add-on, I guess), it returns
        the input exactly.

        card is not used."""
        if self._spreadRev:
            idealIvl = self._fuzzedIvl(idealIvl)
        return idealIvl

    # Dynamic deck handling
    ##########################################################################

    def rebuildDyn(self, did=None):
        "Rebuild a dynamic deck."
        did = did or self.col.decks.selected()
        deck = self.col.decks.get(did)
        assert deck['dyn']
        # move any existing cards back first, then fill
        self.emptyDyn(did)
        ids = self._fillDyn(deck)
        if not ids:
            return
        # and change to our new deck
        self.col.decks.select(did)
        return ids

    def _fillDyn(self, deck):
        search, limit, order = deck['terms'][0]
        orderlimit = self._dynOrder(order, limit)
        if search.strip():
            search = "(%s)" % search
        search = "%s -is:suspended -is:buried -deck:filtered -is:learn" % search
        try:
            ids = self.col.findCards(search, order=orderlimit)
        except:
            ids = []
            return ids
        # move the cards over
        self.col.log(deck['id'], ids)
        self._moveToDyn(deck['id'], ids)
        return ids

    def emptyDyn(self, did, lim=None):
        """Moves cram cards to their deck
        Cards in learning mode move to their previous type.

        Keyword arguments:
        lim -- the query which decides which cards are used
        did -- assuming lim is not provided/false, the (filtered) deck concerned by this call
        """
        if not lim:
            lim = "did = %s" % did
        self.col.log(self.col.db.list("select id from cards where %s" % lim))
        # move out of cram queue
        self.col.db.execute(f"""
update cards set did = odid, queue = (case when type = {CARD_LRN} then {QUEUE_NEW_CRAM}
else type end), type = (case when type = {CARD_LRN} then {CARD_NEW} else type end),
due = odue, odue = 0, odid = 0, usn = ? where %s""" % (lim),
                            self.col.usn())

    def remFromDyn(self, cids):
        self.emptyDyn(None, "id in %s and odid" % ids2str(cids))

    def _dynOrder(self, o, l):
        if o == DYN_OLDEST:
            t = "(select max(id) from revlog where cid=c.id)"
        elif o == DYN_RANDOM:
            t = "random()"
        elif o == DYN_SMALLINT:
            t = "ivl"
        elif o == DYN_BIGINT:
            t = "ivl desc"
        elif o == DYN_LAPSES:
            t = "lapses desc"
        elif o == DYN_ADDED:
            t = "n.id"
        elif o == DYN_REVADDED:
            t = "n.id desc"
        elif o == DYN_DUE:
            t = "c.due"
        elif o == DYN_DUEPRIORITY:
            t = "(case when queue=%d and due <= %d then (ivl / cast(%d-due+0.001 as real)) else 100000+due end)" % (QUEUE_REV,
                    self.today, self.today)
        else:
            # if we don't understand the term, default to due order
            t = "c.due"
        return t + " limit %d" % l

    def _moveToDyn(self, did, ids):
        deck = self.col.decks.get(did)
        data = []
        t = intTime(); u = self.col.usn()
        for c, id in enumerate(ids):
            # start at -100000 so that reviews are all due
            data.append((did, -100000+c, u, id))
        # due reviews stay in the review queue. careful: can't use
        # "odid or did", as sqlite converts to boolean
        queue = f"""
(case when type={CARD_DUE} and (case when odue then odue <= %d else due <= %d end)
 then {QUEUE_REV} else {QUEUE_NEW_CRAM} end)"""
        queue %= (self.today, self.today)
        self.col.db.executemany("""
update cards set
odid = (case when odid then odid else did end),
odue = (case when odue then odue else due end),
did = ?, queue = %s, due = ?, usn = ? where id = ?""" % queue, data)

    def _dynIvlBoost(self, card):
        """New interval for a review card in a dynamic interval.

        Maximum between old interval and
        elapsed*((card.factor/1000)+1.2)/2, with elapsed being the
        time between today and the last review.

        This number is constrained to be between 1 and the parameter
        ```maxIvl``` of the card's configuration.

        """
        assert card.odid and card.type == CARD_DUE
        assert card.factor
        lastReview = (card.odue - card.ivl)
        elapsed = self.today - lastReview
        factor = ((card.factor/1000)+1.2)/2
        ivl = int(max(card.ivl, elapsed * factor, 1))
        conf = self._revConf(card)
        return min(conf['maxIvl'], ivl)

    # Leeches
    ##########################################################################

    def _checkLeech(self, card, conf):
        "Leech handler. True if card was a leech."
        lf = conf['leechFails']
        if not lf:
            return
        # if over threshold or every half threshold reps after that
        if (card.lapses >= lf and
            (card.lapses-lf) % (max(lf // 2, 1)) == 0):
            # add a leech tag
            f = card.note()
            f.addTag("leech")
            f.flush()
            # handle
            a = conf['leechAction']
            if a == 0:
                # if it has an old due, remove it from cram/relearning
                if card.odue:
                    card.due = card.odue
                if card.odid:
                    card.did = card.odid
                card.odue = card.odid = 0
                card.queue = QUEUE_SUSPENDED
            # notify UI
            runHook("leech", card)
            return True

    # Tools
    ##########################################################################

    def _cardConf(self, card):
        """The configuration of this card's deck. See decks.py
        documentation to read more about them."""
        return self.col.decks.confForDid(card.did)

    def _newConf(self, card):
        """The configuration for "new" of this card's deck.See decks.py
        documentation to read more about them.

        """
        conf = self._cardConf(card)
        # normal deck
        if not card.odid:
            return conf['new']
        # dynamic deck; override some attributes, use original deck for others
        oconf = self.col.decks.confForDid(card.odid)
        delays = conf['delays'] or oconf['new']['delays']
        return dict(
            # original deck
            ints=oconf['new']['ints'],
            initialFactor=oconf['new']['initialFactor'],
            bury=oconf['new'].get("bury", True),
            # overrides
            delays=delays,
            separate=conf['separate'],
            order=NEW_CARDS_DUE,
            perDay=self.reportLimit
        )

    def _lapseConf(self, card):
        """The configuration for "lapse" of this card's deck.See decks.py
        documentation to read more about them.

        """
        conf = self._cardConf(card)
        # normal deck
        if not card.odid:
            return conf['lapse']
        # dynamic deck; override some attributes, use original deck for others
        oconf = self.col.decks.confForDid(card.odid)
        delays = conf['delays'] or oconf['lapse']['delays']
        return dict(
            # original deck
            minInt=oconf['lapse']['minInt'],
            leechFails=oconf['lapse']['leechFails'],
            leechAction=oconf['lapse']['leechAction'],
            mult=oconf['lapse']['mult'],
            # overrides
            delays=delays,
            resched=conf['resched'],
        )

    def _revConf(self, card):
        """The configuration for "review" of this card's deck.See decks.py
        documentation to read more about them.

        """
        conf = self._cardConf(card)
        # normal deck
        if not card.odid:
            return conf['rev']
        # dynamic deck
        return self.col.decks.confForDid(card.odid)['rev']

    def _deckLimit(self):
        """The list of active decks, as comma separated parenthesized
        string"""
        return ids2str(self.col.decks.active())

    def _resched(self, card):
        """Whether this review must be taken into account when this
        card to reschedule the card"""
        conf = self._cardConf(card)
        if not conf['dyn']:
            return True
        return conf['resched']

    # Daily cutoff
    ##########################################################################

    def _updateCutoff(self):
        """
        For each deck, set its entry *Today's first element to today's date
        if it's a new day:
        - log the new day
        - unbury new cards
        - change today and daycutoff
        """
        oldToday = self.today
        # days since col created
        self.today = int((time.time() - self.col.crt) // 86400)
        # end of day cutoff
        self.dayCutoff = self.col.crt + (self.today+1)*86400
        if oldToday != self.today:
            self.col.log(self.today, self.dayCutoff)
        # update all daily counts, but don't save decks to prevent needless
        # conflicts. we'll save on card answer instead
        def update(g):
            for t in "new", "rev", "lrn", "time":
                key = t+"Today"
                if g[key][0] != self.today:
                    g[key] = [self.today, 0]
        for deck in self.col.decks.all():
            update(deck)
        # unbury if the day has rolled over
        unburied = self.col.conf.get("lastUnburied", 0)
        if unburied < self.today:
            self.unburyCards()

    def _checkDay(self):
        # check if the day has rolled over
        if time.time() > self.dayCutoff:
            self.reset()

    # Deck finished state
    ##########################################################################

    def finishedMsg(self):
        return ("<b>"+_(
            "Congratulations! You have finished this deck for now.")+
            "</b><br><br>" + self._nextDueMsg())

    def _nextDueMsg(self):
        line = []
        # the new line replacements are so we don't break translations
        # in a point release
        if self.revDue():
            line.append(_("""\
Today's review limit has been reached, but there are still cards
waiting to be reviewed. For optimum memory, consider increasing
the daily limit in the options.""").replace("\n", " "))
        if self.newDue():
            line.append(_("""\
There are more new cards available, but the daily limit has been
reached. You can increase the limit in the options, but please
bear in mind that the more new cards you introduce, the higher
your short-term review workload will become.""").replace("\n", " "))
        if self.haveBuried():
            if self.haveCustomStudy:
                now = " " +  _("To see them now, click the Unbury button below.")
            else:
                now = ""
            line.append(_("""\
Some related or buried cards were delayed until a later session.""")+now)
        if self.haveCustomStudy and not self.col.decks.current()['dyn']:
            line.append(_("""\
To study outside of the normal schedule, click the Custom Study button below."""))
        return "<p>".join(line)

    def revDue(self):
        "True if there are any rev cards due."
        return self.col.db.scalar(
            (f"select 1 from cards where did in %s and queue = {QUEUE_REV} "
             "and due <= ? limit 1") % (self._deckLimit()),
            self.today)

    def newDue(self):
        "True if there are any new cards due."
        return self.col.db.scalar(
            (f"select 1 from cards where did in %s and queue = {QUEUE_NEW_CRAM} "
             "limit 1") % (self._deckLimit(),))

    def haveBuried(self):
        sdids = ids2str(self.col.decks.active())
        cnt = self.col.db.scalar(
            f"select 1 from cards where queue = {QUEUE_USER_BURIED} and did in %s limit 1" % (sdids))
        return not not cnt

    # Next time reports
    ##########################################################################

    def nextIvlStr(self, card, ease, short=False):
        "Return the next interval for CARD as a string."
        ivl = self.nextIvl(card, ease)
        if not ivl:
            return _("(end)")
        s = fmtTimeSpan(ivl, short=short)
        if ivl < self.col.conf['collapseTime']:
            s = "<"+s
        return s

    def nextIvl(self, card, ease):
        "Return the next interval for CARD, in seconds."
        if card.queue in (QUEUE_NEW_CRAM, QUEUE_LRN, QUEUE_DAY_LRN):
            return self._nextLrnIvl(card, ease)
        elif ease == BUTTON_ONE:
            # lapsed
            conf = self._lapseConf(card)
            if conf['delays']:
                return conf['delays'][0]*60
            return self._nextLapseIvl(card, conf)*86400
        else:
            # review
            return self._nextRevIvl(card, ease)*86400

    # this isn't easily extracted from the learn code
    def _nextLrnIvl(self, card, ease):
        if card.queue == QUEUE_NEW_CRAM:
            card.left = self._startingLeft(card)
        conf = self._lrnConf(card)
        if ease == BUTTON_ONE:
            # fail
            return self._delayForGrade(conf, len(conf['delays']))
        elif ease == BUTTON_THREE:
            # early removal
            if not self._resched(card):
                return 0
            return self._graduatingIvl(card, conf, True, adj=False) * 86400
        else:
            left = card.left%1000 - 1
            if left <= 0:
                # graduate
                if not self._resched(card):
                    return 0
                return self._graduatingIvl(card, conf, False, adj=False) * 86400
            else:
                return self._delayForGrade(conf, left)

    # Suspending
    ##########################################################################

    def suspendCards(self, ids):
        "Suspend cards."
        self.col.log(ids)
        self.remFromDyn(ids)
        self.removeLrn(ids)
        self.col.db.execute(
            (f"update cards set queue={QUEUE_SUSPENDED},mod=?,usn=? where id in ")+
            ids2str(ids), intTime(), self.col.usn())

    def unsuspendCards(self, ids):
        "Unsuspend cards."
        self.col.log(ids)
        self.col.db.execute(
            (f"update cards set queue=type,mod=?,usn=? "
            "where queue = {QUEUE_SUSPENDED} and id in ")+ ids2str(ids),
            intTime(), self.col.usn())

    def buryCards(self, cids):
        self.col.log(cids)
        self.remFromDyn(cids)
        self.removeLrn(cids)
        self.col.db.execute((f"""
        update cards set queue={QUEUE_USER_BURIED},mod=?,usn=? where id in """)+ids2str(cids),
                            intTime(), self.col.usn())

    def buryNote(self, nid):
        "Bury all cards for note until next session."
        cids = self.col.db.list(
            "select id from cards where nid = ? and queue >= 0", nid)
        self.buryCards(cids)

    # Sibling spacing
    ##########################################################################

    def _burySiblings(self, card):
        toBury = []
        nconf = self._newConf(card)
        buryNew = nconf.get("bury", True)
        rconf = self._revConf(card)
        buryRev = rconf.get("bury", True)
        # loop through and remove from queues
        for cid,queue in self.col.db.execute(f"""
select id, queue from cards where nid=? and id!=?
and (queue={QUEUE_NEW_CRAM} or (queue={QUEUE_REV} and due<=?))""",
                card.nid, card.id, self.today):
            if queue == QUEUE_REV:
                if buryRev:
                    toBury.append(cid)
                # if bury disabled, we still discard to give same-day spacing
                try:
                    self._revQueue.remove(cid)
                except ValueError:
                    pass
            else:#Queue new Cram
                # if bury disabled, we still discard to give same-day spacing
                if buryNew:
                    toBury.append(cid)
                try:
                    self._newQueue.remove(cid)
                except ValueError:
                    pass
        # then bury
        if toBury:
            self.col.db.execute(
                (f"update cards set queue={QUEUE_USER_BURIED},mod=?,usn=? where id in ")+ids2str(toBury),
                intTime(), self.col.usn())
            self.col.log(toBury)

    # Resetting
    ##########################################################################

    def forgetCards(self, ids):
        "Put cards at the end of the new queue."
        self.remFromDyn(ids)
        self.col.db.execute(
            (f"update cards set type={CARD_NEW},queue={QUEUE_NEW_CRAM},ivl=0,due=0,odue=0,factor=?"
             " where id in ")+ids2str(ids), STARTING_FACTOR)
        pmax = self.col.db.scalar(
            f"select max(due) from cards where type={CARD_NEW}") or 0
        # takes care of mod + usn
        self.sortCards(ids, start=pmax+1)
        self.col.log(ids)

    def reschedCards(self, ids, imin, imax):
        "Put cards in review queue with a new interval in days (min, max)."
        d = []
        t = self.today
        mod = intTime()
        for id in ids:
            r = random.randint(imin, imax)
            d.append(dict(id=id, due=r+t, ivl=max(1, r), mod=mod,
                          usn=self.col.usn(), fact=STARTING_FACTOR))
        self.remFromDyn(ids)
        self.col.db.executemany(f"""
update cards set type={CARD_DUE},queue={QUEUE_REV},ivl=:ivl,due=:due,odue=0,
usn=:usn,mod=:mod,factor=:fact where id=:id""",
                                d)
        self.col.log(ids)

    def resetCards(self, ids):
        "Completely reset cards for export."
        sids = ids2str(ids)
        # we want to avoid resetting due number of existing new cards on export
        nonNew = self.col.db.list(
            f"select id from cards where id in %s and (queue != QUEUE_NEW_CRAM or type != CARD_NEW)"
            % (sids))
        # reset all cards
        self.col.db.execute(
            f"update cards set reps=0,lapses=0,odid=0,odue=0,queue=QUEUE_NEW_CRAM"
            " where id in %s" % (sids)
        )
        # and forget any non-new cards, changing their due numbers
        self.forgetCards(nonNew)
        self.col.log(ids)

    # Repositioning new cards
    ##########################################################################

    def sortCards(self, cids, start=1, step=1, shuffle=False, shift=False):
        scids = ids2str(cids)
        now = intTime()
        nids = []
        nidsSet = set()
        for id in cids:
            nid = self.col.db.scalar("select nid from cards where id = ?", id)
            if nid not in nidsSet:
                nids.append(nid)
                nidsSet.add(nid)
        if not nids:
            # no new cards
            return
        # determine nid ordering
        due = {}
        if shuffle:
            random.shuffle(nids)
        for c, nid in enumerate(nids):
            due[nid] = start+c*step
        # pylint: disable=undefined-loop-variable
        high = start+c*step
        # shift?
        if shift:
            low = self.col.db.scalar(
                f"select min(due) from cards where due >= ? and type = {CARD_NEW} "
                "and id not in %s" % (scids),
                start)
            if low is not None:
                shiftby = high - low + 1
                self.col.db.execute(f"""
update cards set mod=?, usn=?, due=due+? where id not in %s
and due >= ? and queue = {QUEUE_NEW_CRAM}""" % (scids), now, self.col.usn(), shiftby, low)
        # reorder cards
        d = []
        for id, nid in self.col.db.execute(
            (f"select id, nid from cards where type = {CARD_NEW} and id in ")+scids):
            d.append(dict(now=now, due=due[nid], usn=self.col.usn(), cid=id))
        self.col.db.executemany(
            "update cards set due=:due,mod=:now,usn=:usn where id = :cid", d)

    def randomizeCards(self, did):
        cids = self.col.db.list("select id from cards where did = ?", did)
        self.sortCards(cids, shuffle=True)

    def orderCards(self, did):
        cids = self.col.db.list("select id from cards where did = ? order by id", did)
        self.sortCards(cids)

    def resortConf(self, conf):
        for did in self.col.decks.didsForConf(conf):
            if conf['new']['order'] == 0:
                self.randomizeCards(did)
            else:
                self.orderCards(did)

    # for post-import
    def maybeRandomizeDeck(self, did=None):
        if not did:
            did = self.col.decks.selected()
        conf = self.col.decks.confForDid(did)
        # in order due?
        if conf['new']['order'] == NEW_CARDS_RANDOM:
            self.randomizeCards(did)
