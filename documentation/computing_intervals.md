# Computing the next review interval

The manual kind of let you guess how the
[intervals](https://apps.ankiweb.net/docs/manual.html#reviews) are
computed. But actually, you never get the real number, unless you read
the code. So, here is the exact rules.


For the new cards (in learning
cards), it is in method ```_answerLrncard```. For the review cards, it
is in methods ```_answerRevCard``` and ```_rescheduleRev```.

## Parameters
We first list the parameters taken into account.

### Last interval
Last time you reviewed a card, an interval was assigned to it. It is
taken into account to compute the new interval. Unless this is a new
card.

### Easyness factor
Each card have a parameter called its easyness. TODO

### Delay
If you are late reviewing your card, we also take into account how
late you are. This is called the delay of the card.

## The formulas
The methods mentionned below appear in ```anki.sched.Scheduler```.

### Filtered deck
If the card is in filtered deck, if the filter option "reschedule
cards based on my answers in this deck" is not checked, then the
interval is not modified and this review is not taken into account. We
now assume that this option is checked

#### Lapse
Note that if you review a card in advance, it's next due date can only
increase. If you lapsed the card, it won't be taken into account. Only
success are taken into account. However, if the card was already due,
then the new interval is taken into account.

(Technically, the due date is the max between the old due date, and
the due date planned by this review)

#### Successful review
The new interval is the maximum between old interval and
elapsed*((easyness factor/1000)+1.2)/2, with elapsed being the time
between today and the last review.

This number is constrained to be between 1 and the ```maxIvl``` of the
card's configuration.

This formula is in the method ```_dynIvlBoost```.


### Again
This case is quite easy.

When graduating again, the new interval is tomorrow Its done in
```_rescheduleAsRev```




### Cards in learning (new cards and lapse)
This is computed in ```_answerLrnCard```.
