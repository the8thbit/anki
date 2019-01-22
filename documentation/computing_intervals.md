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

### Easyness
Each card have a parameter called its easyness. TODO

### Delay
If you are late reviewing your card, we also take into account how
late you are. This is called the delay of the card.

## The formula
The methods mentionned below appear in ```anki.sched.Scheduler```.

### Filtered deck
If the card is in filtered deck, if the filter option "reschedule
cards based on my answers in this deck" is not checked, then the
interval is not modified and this review is not taken into account.

### Again

### Cards in learning (new cards and lapse)
This is computed in ```_answerLrnCard```.
