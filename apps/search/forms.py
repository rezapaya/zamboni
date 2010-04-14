import collections
import itertools

from django import forms
from django.forms.util import ErrorDict

from tower import ugettext as _, ugettext_lazy as _lazy

import amo
from amo import helpers
from applications.models import AppVersion

types = (amo.ADDON_ANY, amo.ADDON_EXTENSION, amo.ADDON_THEME,
         amo.ADDON_DICT, amo.ADDON_SEARCH, amo.ADDON_LPAPP)

updated = (
    ('', _lazy(u'Any time')),
    ('1 day ago', _lazy(u'Past Day')),
    ('1 week ago', _lazy(u'Past Week')),
    ('1 month ago', _lazy(u'Past Month')),
    ('3 months ago', _lazy(u'Past 3 Months')),
    ('6 months ago', _lazy(u'Past 6 Months')),
    ('1 year ago', _lazy(u'Past Year')),
)

sort_by = (
    ('', _lazy(u'Keyword Match')),
    ('newest', _lazy(u'Newest', 'advanced_search_form_newest')),
    ('name', _lazy(u'Name', 'advanced_search_form_name')),
    ('averagerating', _lazy(u'Rating', 'advanced_search_form_rating')),
    ('weeklydownloads', _lazy(u'Popularity',
                              'advanced_search_form_popularity')),
)

per_page = (20, 50, 100)

tuplize = lambda x: divmod(int(x * 10), 10)

# These releases were so minor that we don't want to search for them.
skip_versions = collections.defaultdict(list)
skip_versions[amo.FIREFOX] = (tuplize(v) for v in amo.FIREFOX.exclude_versions)

min_version = collections.defaultdict(lambda: (0, 0))
min_version.update({
    amo.FIREFOX: tuplize(amo.FIREFOX.min_display_version),
    amo.THUNDERBIRD: tuplize(amo.THUNDERBIRD.min_display_version),
    amo.SEAMONKEY: tuplize(amo.SEAMONKEY.min_display_version),
    amo.SUNBIRD: tuplize(amo.SUNBIRD.min_display_version),
})


def get_app_versions():
    rv = {}
    for id, app in amo.APP_IDS.items():
        min_ver, skip = min_version[app], skip_versions[app]
        versions = [(a.major, a.minor1) for a in
                    AppVersion.objects.filter(application=id)]
        groups = itertools.groupby(sorted(versions))
        strings = ['%s.%s' % v for v, group in groups
                   if v >= min_ver and v not in skip]
        rv[id] = [(s, s) for s in strings] + [(_('Any'), 'any')]
    return rv


# Fake categories to slip some add-on types into the search groups.
_Cat = collections.namedtuple('Cat', 'id name weight type_id')


def get_search_groups(app):
    sub = []
    for type_ in (amo.ADDON_DICT, amo.ADDON_SEARCH, amo.ADDON_THEME):
        sub.append(_Cat(0, amo.ADDON_TYPES[type_], 0, type_))
    sub.extend(helpers.sidebar(app)[0])
    sub = [('%s,%s' % (a.type_id, a.id), a.name) for a in
           sorted(sub, key=lambda x: (x.weight, x.name))]
    top_level = [('all', _('all add-ons')),
                 ('collections', _('all collections')),
                 ('personas', _('all personas'))]
    return top_level[:1] + sub + top_level[1:], top_level


def SearchForm(request):

    search_groups, top_level = get_search_groups(request.APP or amo.FIREFOX)

    class _SearchForm(forms.Form):
        q = forms.CharField(required=False)

        cat = forms.ChoiceField(choices=search_groups, required=False)

        appid = forms.TypedChoiceField(label=_('Application'),
            choices=[(app.id, app.pretty) for app in amo.APP_USAGE],
            required=False, coerce=int)

        # This gets replaced by a <select> with js.
        lver = forms.CharField(label=_('Version'), required=False)

        atype = forms.TypedChoiceField(label=_('Type'),
            choices=[(t, amo.ADDON_TYPE[t]) for t in types], required=False,
            coerce=int, empty_value=amo.ADDON_ANY)

        pid = forms.TypedChoiceField(label=_('Platform'),
                choices=[(p[0], p[1].name) for p in amo.PLATFORMS.iteritems()
                         if p[1] != amo.PLATFORM_ANY], required=False,
                coerce=int, empty_value=amo.PLATFORM_ALL.id)

        lup = forms.ChoiceField(label=_('Last Updated'), choices=updated,
                                required=False)

        sort = forms.ChoiceField(label=_('Sort By'), choices=sort_by,
                                 required=False)

        pp = forms.TypedChoiceField(label=_('Per Page'),
               choices=zip(per_page, per_page), required=False, coerce=int,
               empty_value=per_page[0])

        advanced = forms.BooleanField(widget=forms.HiddenInput, required=False)
        tag = forms.CharField(widget=forms.HiddenInput, required=False)
        page = forms.IntegerField(widget=forms.HiddenInput, required=False)

        # Attach these to the form for usage in the template.
        get_app_versions = staticmethod(get_app_versions)
        top_level_cat = dict(top_level)
        queryset = AppVersion.objects.filter(id__in=amo.APP_IDS)

        # TODO(jbalogh): when we start using this form for zamboni search, it
        # should check that the appid and lver match up using app_versions.

        def clean(self):
            d = self.cleaned_data

            # Set some defaults
            if not d.get('appid'):
                d['appid'] = request.APP.id

            if 'cat' in d:
                if ',' in d['cat']:
                    (d['atype'], d['cat']) = map(int, d['cat'].split(','))
                elif d['cat'] == 'all':
                    d['cat'] = None

            if 'page' not in d or not d['page']:
                d['page'] = 1
            return d

        def full_clean(self):
            """
            Cleans all of self.data and populates self._errors and
            self.cleaned_data.
            Does not remove cleaned_data if there are errors.
            """
            self._errors = ErrorDict()
            if not self.is_bound:  # Stop further processing.
                return
            self.cleaned_data = {}
            # If the form is permitted to be empty, and none of the form data
            # has changed from the initial data, short circuit any validation.
            if self.empty_permitted and not self.has_changed():
                return
            self._clean_fields()
            self._clean_form()

    d = request.GET.copy()

    return _SearchForm(d)
