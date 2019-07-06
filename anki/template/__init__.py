from anki.template.template import Template
from anki.template.view import View

def renderAndIsFieldPresent(template, context=None, **kwargs):
    """
    Given the template and its fields, create the html of the card.

    template -- a template with mustache
    context -- a dictionnary of fields, also containing the value for
    Tags, Type, Deck, Subdeck, Fields, FrontSide (on the
    back). Containing "cn:1" with n the ord of the field
    kwargs -- more context, passed as function argument
    """
    context = context and context.copy() or {}
    context.update(kwargs)
    return Template(template, context).render()

def render(template, context=None, **kwargs):
    return renderAndIsFieldPresent(template, context=context, **kwargs)[0]
