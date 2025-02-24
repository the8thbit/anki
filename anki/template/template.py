import re
from anki.utils import stripHTML, stripHTMLMedia
from anki.hooks import runFilter
from anki.template import furigana; furigana.install()
from anki.template import hint; hint.install()

clozeReg = r"(?si)\{\{(c)%s::(.*?)(::(.*?))?\}\}"
"""clozeReg % n is the regexp recognizing the occurrences of close number n.
   clozeReg %.+? is the regexp recognizing any cloze occurrence.
   group 0 is c. Group 1 is the cloze, group 2 is the hint with ::, group 3 is the hint.
"""
#(?si) means .dot match all strings, ignore case

modifiers = {}
def modifier(symbol):
    """Decorator for associating a function with a Mustache tag modifier.

    @modifier('P')
    def render_tongue(self, tag_name=None, context=None):
        return ":P %s" % tag_name

    {{P yo }} => :P yo
    """
    def set_modifier(func):
        modifiers[symbol] = func
        return func
    return set_modifier


def get_or_attr(obj, name, default=None):
    """If its a susbscriptable: obj[name]. Else obj.name. Else default"""
    try:
        return obj[name]
    except KeyError:
        return default
    except:
        try:
            return getattr(obj, name)
        except AttributeError:
            return default


class Template:
    """TODO

    A template object contains:
    template -- ; see ../models.py
    context -- a dictionnary containing at least:
    ** the fields
    ** the  value for Tags, Type, Deck, Subdeck, Fields, FrontSide (on
    the  back).
    ** Containing "cn:1" with n the ord of the field
    """
    # The regular expression used to find a #section
    # I.e. {{# or {{^
    # from {{#foo}}bar{{/foo}} return ({{#foo}}bar{{/foo}},foo,bar)
    section_re = None

    # The regular expression used to find a tag.  The tag can start by
    # #, =, &, !, >,{ or the empty string.
    # from {{sfoo}} return ({{sfoo}},s,foo)
    tag_re = None

    # Opening tag delimiter
    otag = '{{'

    # Closing tag delimiter
    ctag = '}}'

    def __init__(self, template, context=None):
        self.template = template
        self.context = context or {}
        self.compile_regexps()

    def render(self, template=None, context=None, encoding=None):
        """Turns a Mustache template into something wonderful."""
        template = template or self.template
        context = context or self.context

        self.showAField = False
        template = self.render_sections(template, context)
        result = self.render_tags(template, context)
        if encoding is not None:
            result = result.encode(encoding)
        return result, self.showAField

    def renderAndIsFieldPresent(self, template=None, context=None, encoding=None):
        """A pair with:
        * Turns a Mustache template into something wonderful.
        * whether a field was shown"""
        template = template or self.template
        context = context or self.context

        self.showAField = False
        template = self.render_sections(template, context)
        result = self.render_tags(template, context)
        if encoding is not None:
            result = result.encode(encoding)
        return result, self.showAField

    def compile_regexps(self):
        """Compiles our section and tag regular expressions."""
        #Opening and closing tag. Currently {{ and }}
        tags = { 'otag': re.escape(self.otag), 'ctag': re.escape(self.ctag) }

        # See the comment for section_re
        section = r"%(otag)s[\#|^]([^\}]*)%(ctag)s(.+?)%(otag)s/\1%(ctag)s"
        self.section_re = re.compile(section % tags, re.M|re.S)

        # See the comment for tag_re
        tag = r"%(otag)s(#|=|&|!|>|\{)?(.+?)\1?%(ctag)s+"
        self.tag_re = re.compile(tag % tags)

    def sub_section(self, match, context):
        section, section_name, inner = match.group(0, 1, 2)
        section_name = section_name.strip()

        # val will contain the content of the field considered
        # right now
        val = None
        m = re.match("c[qa]:(\d+):(.+)", section_name)
        if m:
            # get full field text
            txt = get_or_attr(context, m.group(2), None)
            m = re.search(clozeReg%m.group(1), txt)
            if m:
                val = m.group(1)
        else:
            val = get_or_attr(context, section_name, None)
        replacer = ''
        # Whether it's {{^
        inverted = section[2] == "^"
        # Ensuring we don't consider whitespace in wval
        if val:
            val = stripHTMLMedia(val).strip()
        if (val and not inverted) or (not val and inverted):
                replacer = inner
        return replacer

    def render_sections(self, template, context):
        """replace {{#foo}}bar{{/foo}} and {{^foo}}bar{{/foo}} by
        their normal value."""
        n = 1
        while n:
            template, n = self.section_re.subn(lambda match:self.sub_section(match,context), template)
        return template

    def sub_tag(self, match, context):
        tag, tag_type, tag_name = match.group(0, 1, 2)
        # i.e. "{{!foo}}", "!", "foo"
        tag_name = tag_name.strip()
        func = modifiers[tag_type]
        replacement = func(self, tag_name, context)
        return replacement

    def render_tags(self, template, context):
        """A pair with:
        * All the tags in a template for a context. Normally
        {{# and {{^ are removed,
        * whether a field is shown"""
        repCount = 0
        try:
            return self.tag_re.sub(lambda match: self.sub_tag(match, context),template)
        except (SyntaxError, KeyError):
            return "{{invalid template}}"

    # {{{ functions just like {{ in anki
    @modifier('{')
    def render_tag(self, tag_name, context):
        return self.render_unescaped(tag_name, context)

    @modifier('!')
    def render_comment(self, tag_name=None, context=None):
        """Rendering a comment always returns nothing."""
        return ''

    @modifier(None)
    def render_unescaped(self, tag_name=None, context=None):
        """Render a tag without escaping it."""
        txt = get_or_attr(context, tag_name)
        if txt is not None:
            # some field names could have colons in them
            # avoid interpreting these as field modifiers
            # better would probably be to put some restrictions on field names
            if txt.strip():
                self.showAField = True
            return txt

        # field modifiers
        parts = tag_name.split(':')
        extra = None
        if len(parts) == 1 or parts[0] == '':
            return '{unknown field %s}' % tag_name
        else:
            mods, tag = parts[:-1], parts[-1] #py3k has *mods, tag = parts

        txt = get_or_attr(context, tag)

        #Since 'text:' and other mods can affect html on which Anki relies to
        #process clozes, we need to make sure clozes are always
        #treated after all the other mods, regardless of how they're specified
        #in the template, so that {{cloze:text: == {{text:cloze:
        #For type:, we return directly since no other mod than cloze (or other
        #pre-defined mods) can be present and those are treated separately
        mods.reverse()
        mods.sort(key=lambda s: not s=="type")

        for mod in mods:
            # built-in modifiers
            if mod == 'text':
                # strip html
                txt = stripHTML(txt) if txt else ""
            elif mod == 'type':
                # type answer field; convert it to [[type:...]] for the gui code
                # to process
                return "[[%s]]" % tag_name
            elif mod.startswith('cq-') or mod.startswith('ca-'):
                # cloze deletion
                mod, extra = mod.split("-")
                txt = self.clozeText(txt, extra, mod[1]) if txt and extra else ""
            else:
                # hook-based field modifier
                mod, extra = re.search(r"^(.*?)(?:\((.*)\))?$", mod).groups()
                txt = runFilter('fmod_' + mod, txt or '', extra or '', context,
                                tag, tag_name)
                if txt is None:
                    return '{unknown field %s}' % tag_name
        return txt

    def clozeText(self, txt, ord, type):
        reg = clozeReg
        if not re.search(reg%ord, txt):
            return ""
        txt = self._removeFormattingFromMathjax(txt, ord)
        def repl(m):
            # replace chosen cloze with type
            if type == "q":
                if m.group(4):
                    buf = "[%s]" % m.group(4)
                else:
                    buf = "[...]"
            else:
                buf = m.group(2)
            # uppercase = no formatting
            if m.group(1) == "c":
                buf = "<span class=cloze>%s</span>" % buf
            return buf
        txt = re.sub(reg%ord, repl, txt)
        # and display other clozes normally
        return re.sub(reg%r"\d+", "\\2", txt)

    # look for clozes wrapped in mathjax, and change {{cx to {{Cx
    def _removeFormattingFromMathjax(self, txt, ord):
        opening = ["\\(", "\\["]
        closing = ["\\)", "\\]"]
        # flags in middle of expression deprecated
        creg = clozeReg.replace("(?si)", "")
        regex = r"(?si)(\\[([])(.*?)"+(creg%ord)+r"(.*?)(\\[\])])"
        def repl(m):
            enclosed = True
            for s in closing:
                if s in m.group(1):
                    enclosed = False
            for s in opening:
                if s in m.group(7):
                    enclosed = False
            if not enclosed:
                return m.group(0)
            # remove formatting
            return m.group(0).replace("{{c", "{{C")
        txt = re.sub(regex, repl, txt)
        return txt

    @modifier('=')
    def render_delimiter(self, tag_name=None, context=None):
        """Changes the Mustache delimiter."""
        try:
            self.otag, self.ctag = tag_name.split(' ')
        except ValueError:
            # invalid
            return
        self.compile_regexps()
        return ''
