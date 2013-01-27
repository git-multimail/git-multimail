#! /usr/bin/env python2

# Copyright (c) 2012,2013 Michael Haggerty
# Derived from contrib/hooks/post-receive-email, which is
# Copyright (c) 2007 Andy Parkins
# and also includes contributions by other authors.
#
# This file is part of git-multimail.
#
# git-multimail is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License version
# 2 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see
# <http://www.gnu.org/licenses/>.

"""Generate notification emails for pushes to a git repository.

This hook sends emails describing changes introduced by pushes to a
git repository.  For each reference that was changed, it emits one
ReferenceChange email summarizing how the reference was changed,
followed by one Revision email for each new commit that was introduced
by the reference change.

Each commit is announced in exactly one Revision email.  If the same
commit is merged into another branch in the same or a later push, then
the ReferenceChange email will list the commit's SHA1 and its one-line
summary, but no new Revision email will be generated.

This script is designed to be used as a "post-receive" hook in a git
repository (see githooks(5)).  It can also be used as an "update"
script, but this usage is not completely reliable and is deprecated.

To help with debugging, this script accepts a --stdout option, which
causes the emails to be written to standard output rather than sent
using sendmail.

See the accompanying README file for the complete documentation.

"""

import sys
import os
import re
import bisect
import subprocess
import email.utils
import optparse
from email.utils import getaddresses
from email.utils import formataddr


DEBUG = False

ZEROS = '0' * 40
LOGBEGIN = '- Log -----------------------------------------------------------------\n'
LOGEND = '-----------------------------------------------------------------------\n'


HEADER_TEMPLATE = """\
To: %(recipients)s
Subject: %(emailprefix)s%(refname_type)s %(short_refname)s %(change_type)sd
Content-Type: text/plain; charset=utf-8
Message-ID: %(msgid)s
From: %(sender)s
Reply-To: %(pusher_email)s
X-Git-Repo: %(repo_shortname)s
X-Git-Refname: %(refname)s
X-Git-Reftype: %(refname_type)s
X-Git-Oldrev: %(oldrev)s
X-Git-Newrev: %(newrev)s
Auto-Submitted: auto-generated

This is an automated email from the git hooks/post-receive script.

%(pusher)s pushed a change to %(refname_type)s %(short_refname)s
in repository %(repo_shortname)s.

"""


FOOTER_TEMPLATE = """\

-- \n\
To stop receiving notification emails like this one, please contact
%(administrator)s.
"""


REWIND_ONLY_TEMPLATE = """\
This update removed existing revisions from the reference, leaving the
reference pointing at a previous point in the repository history.

 * -- * -- N   %(refname)s (%(newrev_short)s)
            \\
             O -- O -- O   (%(oldrev_short)s)

Any revisions marked "omits" are not gone; other references still
refer to them.  Any revisions marked "discards" are gone forever.
"""


NON_FF_TEMPLATE = """\
This update added new revisions after undoing existing revisions.
That is to say, some revisions that were in the old version of the
%(refname_type)s are not in the new version.  This situation occurs
when a user --force pushes a change and generates a repository
containing something like this:

 * -- * -- B -- O -- O -- O   (%(oldrev_short)s)
            \\
             N -- N -- N   %(refname)s (%(newrev_short)s)

You should already have received notification emails for all of the O
revisions, and so the following emails describe only the N revisions
from the common base, B.

Any revisions marked "omits" are not gone; other references still
refer to them.  Any revisions marked "discards" are gone forever.
"""


NO_NEW_REVISIONS_TEMPLATE = """\
No new revisions were added by this update.
"""


DISCARDED_REVISIONS_TEMPLATE = """\
This change permanently discards the following revisions:
"""


NO_DISCARDED_REVISIONS_TEMPLATE = """\
The revisions that were on this %(refname_type)s are still contained in
other references; therefore, this change does not discard any commits
from the repository.
"""


NEW_REVISIONS_TEMPLATE = """\
The %(tot)s revisions listed above as "new" are entirely new to this
repository and will be described in separate emails.  The revisions
listed as "adds" were already present in the repository and have only
been added to this reference.

"""


TAG_CREATED_TEMPLATE = """\
        at  %(newrev_short)s (%(newrev_type)s)
"""


TAG_UPDATED_TEMPLATE = """\
*** WARNING: tag %(short_refname)s was modified! ***

      from  %(oldrev_short)s (%(oldrev_type)s)
        to  %(newrev_short)s (%(newrev_type)s)
"""


TAG_DELETED_TEMPLATE = """\
*** WARNING: tag %(short_refname)s was deleted! ***

"""


NON_COMMIT_UPDATE_TEMPLATE = """\
This is an unusual reference change because the reference did not
refer to a commit either before or after the change.  We do not know
how to provide full information about this reference change.
"""


REVISION_HEADER_TEMPLATE = """\
To: %(recipients)s
Subject: %(emailprefix)s%(num)02d/%(tot)02d: %(oneline)s
Content-Type: text/plain; charset=utf-8
From: %(sender)s
Reply-To: %(author)s
In-Reply-To: %(reply_to_msgid)s
X-Git-Repo: %(repo_shortname)s
X-Git-Refname: %(refname)s
X-Git-Reftype: %(refname_type)s
X-Git-Rev: %(rev)s
Auto-Submitted: auto-generated

This is an automated email from the git hooks/post-receive script.

%(pusher)s pushed a commit to %(refname_type)s %(short_refname)s
in repository %(repo_shortname)s.

"""


REVISION_FOOTER_TEMPLATE = FOOTER_TEMPLATE


class CommandError(Exception):
    def __init__(self, cmd, retcode):
        self.cmd = cmd
        self.retcode = retcode
        Exception.__init__(
            self,
            'Command "%s" failed with retcode %s' % (' '.join(cmd), retcode,)
            )


class ConfigurationException(Exception):
    pass


def read_output(cmd, input=None, keepends=False, **kw):
    if input:
        stdin = subprocess.PIPE
    else:
        stdin = None
    p = subprocess.Popen(
        cmd, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw
        )
    (out, err) = p.communicate(input)
    retcode = p.wait()
    if retcode:
        raise CommandError(cmd, retcode)
    if not keepends:
        out = out.rstrip('\n\r')
    return out


def read_lines(cmd, keepends=False, **kw):
    """Return the lines output by command.

    Return as single lines, with newlines stripped off."""

    return read_output(cmd, keepends=True, **kw).splitlines(keepends)


class Config(object):
    def __init__(self, section):
        self.section = section

    @staticmethod
    def _split(s):
        """Split NUL-terminated values."""

        words = s.split('\0')
        assert words[-1] == ''
        return words[:-1]

    def get(self, name, default=''):
        try:
            values = self._split(read_output(
                    ['git', 'config', '--get', '--null', '%s.%s' % (self.section, name)],
                    keepends=True,
                    ))
            assert len(values) == 1
            return values[0]
        except CommandError:
            return default

    def get_bool(self, name, default=None):
        try:
            value = read_output(
                ['git', 'config', '--get', '--bool', '%s.%s' % (self.section, name)]
                )
        except CommandError:
            return default
        return value == 'true'

    def get_all(self, name, default=None):
        """Read a (possibly multivalued) setting from the configuration.

        Return the result as a list of values, or default if the name
        is unset."""

        try:
            return self._split(read_output(
                ['git', 'config', '--get-all', '--null', '%s.%s' % (self.section, name)],
                keepends=True,
                ))
        except CommandError, e:
            if e.retcode == 1:
                return default
            else:
                raise

    def get_recipients(self, name, default=None):
        """Read a recipients list from the configuration.

        Return the result as a comma-separated list of email
        addresses, or default if the option is unset.  If the setting
        has multiple values, concatenate them with comma separators."""

        lines = self.get_all(name, default=None)
        if lines is None:
            return default
        return ', '.join(line.strip() for line in lines)

    def set(self, name, value):
        read_output(['git', 'config', '%s.%s' % (self.section, name), value])

    def add(self, name, value):
        read_output(['git', 'config', '--add', '%s.%s' % (self.section, name), value])

    def has_key(self, name):
        return self.get_all(name, default=None) is not None

    def unset_all(self, name):
        try:
            read_output(['git', 'config', '--unset-all', '%s.%s' % (self.section, name)])
        except CommandError, e:
            if e.retcode == 5:
                # The name doesn't exist, which is what we wanted anyway...
                pass
            else:
                raise

    def set_recipients(self, name, value):
        self.unset_all(name)
        for pair in getaddresses([value]):
            self.add(name, formataddr(pair))


def read_log_oneline(*log_args):
    """Generate a one-line summary for each revision requested.

    The arguments are strings that will be passed directly to "git
    log" as revision selectors."""

    cmd = [
        'git', 'log', '--abbrev=10', '--format=%h %s',
        ] + list(log_args) + ['--']
    return read_lines(cmd)


def limit_lines(lines, max_lines):
    for (index, line) in enumerate(lines):
        if index < max_lines:
            yield line

    if index >= max_lines:
        yield '... %d lines suppressed ...\n' % (index + 1 - max_lines,)


def limit_linelength(lines, max_linelength):
    for line in lines:
        # Don't forget that lines always include a trailing newline.
        if len(line) > max_linelength + 1:
            line = line[:max_linelength - 7] + ' [...]\n'
        yield line


class CommitSet(object):
    """A (constant) set of object names.

    The set should be initialized with full SHA1 object names.  The
    __contains__() method returns True iff its argument is an
    abbreviation of any the names in the set."""

    def __init__(self, names):
        self._names = sorted(names)

    def __len__(self):
        return len(self._names)

    def __contains__(self, sha1_abbrev):
        """Return True iff this set contains sha1_abbrev (which might be abbreviated)."""

        i = bisect.bisect_left(self._names, sha1_abbrev)
        return i < len(self) and self._names[i].startswith(sha1_abbrev)


class GitObject(object):
    def __init__(self, sha1, type=None):
        if sha1 == ZEROS:
            self.sha1 = self.type = self.commit = None
        else:
            self.sha1 = sha1
            self.type = type or read_output(['git', 'cat-file', '-t', self.sha1])

            if self.type == 'commit':
                self.commit = self
            elif self.type == 'tag':
                try:
                    self.commit = GitObject(
                        read_output(['git', 'rev-parse', '--verify', '%s^0' % (self.sha1,)]),
                        type='commit',
                        )
                except CommandError:
                    self.commit = None
            else:
                self.commit = None

        self.short = read_output(['git', 'rev-parse', '--short=10', sha1])

    def __eq__(self, other):
        return isinstance(other, GitObject) and self.sha1 == other.sha1

    def __hash__(self):
        return hash(self.sha1)

    def __nonzero__(self):
        return bool(self.sha1)

    def __str__(self):
        return self.sha1 or ZEROS


class Change(object):
    """A Change that has been made to the Git repository.

    Abstract class from which both Revisions and ReferenceChanges are
    derived.  A Change knows how to generate a notification email
    describing itself."""

    def __init__(self, environment):
        self.environment = environment
        self._values = None

    def _compute_values(self):
        """Return a dictionary {keyword : expansion} for this Change.

        Derived classes overload this method to add more entries to
        the return value.  This method is used internally by
        get_values().  The return value should always be a new
        dictionary."""

        return self.environment.get_values()

    def get_values(self, **extra_values):
        """Return a dictionary {keyword : expansion} for this Change.

        Return a dictionary mapping keywords to the values that they
        should be expanded to for this Change (used when interpolating
        template strings).  If any keyword arguments are supplied, add
        those to the return value as well.  The return value is always
        a new dictionary."""

        if self._values is None:
            self._values = self._compute_values()

        values = self._values.copy()
        if extra_values:
            values.update(extra_values)
        return values

    def expand(self, template, **extra_values):
        """Expand template.

        Expand the template (which should be a string) using string
        interpolation of the values for this Change.  If any keyword
        arguments are provided, also include those in the keywords
        available for interpolation."""

        return template % self.get_values(**extra_values)

    def expand_lines(self, template, **extra_values):
        """Break template into lines and expand each line.

        Silently skip lines that contain references to unknown
        variables."""

        values = self.get_values(**extra_values)
        for line in template.splitlines(True):
            try:
                yield line % values
            except KeyError, e:
                if DEBUG:
                    sys.stderr.write(
                        'Warning: unknown variable %r in the following line; line skipped:\n'
                        '    %s'
                        % (e.args[0], line,)
                        )

    def generate_email_header(self):
        """Generate the email header for this Change, a line at a time.

        The header should include the RFC 2822 email header, a blank
        line, plus any standard boilerplate to be included at the top
        of the email body."""

        raise NotImplementedError()

    def generate_email_body(self):
        """Generate the main part of the email body, a line at a time.

        The text in the body might be truncated after a specified
        number of lines (see multimailhook.emailmaxlines)."""

        raise NotImplementedError()

    def generate_email_footer(self):
        """Generate the footer of the email, a line at a time.

        The footer is always included, irrespective of
        multimailhook.emailmaxlines."""

        raise NotImplementedError()

    def generate_email(self, push, body_filter=None):
        """Generate an email describing this change.

        Iterate over the lines (including the header lines) of an
        email describing this change.  If body_filter is not None,
        then use it to filter the lines that are intended for the
        email body."""

        for line in self.generate_email_header():
            yield line

        body = self.generate_email_body(push)
        if body_filter is not None:
            body = body_filter(body)
        for line in body:
            yield line

        for line in self.generate_email_footer():
            yield line


class Revision(Change):
    """A Change consisting of a single git commit."""

    def __init__(self, reference_change, rev, num, tot):
        Change.__init__(self, reference_change.environment)
        self.reference_change = reference_change
        self.rev = rev
        self.change_type = self.reference_change.change_type
        self.refname = self.reference_change.refname
        self.num = num
        self.tot = tot
        self.recipients = self.environment.get_revision_recipients(self)

    def _compute_values(self):
        values = Change._compute_values(self)

        # First line of commit message:
        try:
            oneline = read_output(
                ['git', 'log', '--format=%s', '--max-count=1', self.rev.sha1]
                )
        except CommandError:
            oneline = self.rev.sha1

        values['rev'] = self.rev.sha1
        values['rev_short'] = self.rev.short
        values['change_type'] = self.change_type
        values['refname'] = self.refname
        values['short_refname'] = self.reference_change.short_refname
        values['refname_type'] = self.reference_change.refname_type
        values['reply_to_msgid'] = self.reference_change.msgid
        values['num'] = self.num
        values['tot'] = self.tot
        values['recipients'] = self.recipients
        values['oneline'] = oneline

        try:
            values['author'] = self.get_author()
        except UnknownUserError:
            pass

        return values

    def get_author(self):
        return read_output(['git', 'log', '--max-count=1', '--format=%aN <%aE>', self.rev.sha1])

    def generate_email_header(self):
        return self.expand_lines(REVISION_HEADER_TEMPLATE)

    def generate_email_body(self, push):
        """Show this revision."""

        return read_lines(
            [
                'git', 'log', '--find-renames', '--find-copies',
                 '--stat', '--patch', '--cc',
                '-1', self.rev.sha1,
                ],
            keepends=True,
            )

    def generate_email_footer(self):
        return self.expand_lines(REVISION_FOOTER_TEMPLATE)


class ReferenceChange(Change):
    """A Change to a Git reference.

    An abstract class representing a create, update, or delete of a
    Git reference.  Derived classes handle specific types of reference
    (e.g., tags vs. branches).  These classes generate the main
    reference change email summarizing the reference change and
    whether it caused any any commits to be added or removed.

    ReferenceChange objects are usually created using the static
    create() method, which has the logic to decide which derived class
    to instantiate."""

    REF_RE = re.compile(r'^refs\/(?P<area>[^\/]+)\/(?P<shortname>.*)$')

    @staticmethod
    def create(environment, oldrev, newrev, refname):
        """Return a ReferenceChange object representing the change.

        Return an object that represents the type of change that is being
        made. oldrev and newrev should be SHA1s or ZEROS."""

        old = GitObject(oldrev)
        new = GitObject(newrev)
        rev = new or old

        # The revision type tells us what type the commit is, combined with
        # the location of the ref we can decide between
        #  - working branch
        #  - tracking branch
        #  - unannotated tag
        #  - annotated tag
        m = ReferenceChange.REF_RE.match(refname)
        if m:
            area = m.group('area')
            short_refname = m.group('shortname')
        else:
            area = ''
            short_refname = refname

        if rev.type == 'tag':
            # Annotated tag:
            klass = AnnotatedTagChange
        elif rev.type == 'commit':
            if area == 'tags':
                # Non-annotated tag:
                klass = NonAnnotatedTagChange
            elif area == 'heads':
                # Branch:
                klass = BranchChange
            elif area == 'remotes':
                # Tracking branch:
                sys.stderr.write(
                    '*** Push-update of tracking branch %r\n'
                    '***  - incomplete email generated.\n'
                     % (refname,)
                    )
                klass = OtherReferenceChange
            else:
                # Some other reference namespace:
                sys.stderr.write(
                    '*** Push-update of strange reference %r\n'
                    '***  - incomplete email generated.\n'
                     % (refname,)
                    )
                klass = OtherReferenceChange
        else:
            # Anything else (is there anything else?)
            sys.stderr.write(
                '*** Unknown type of update to %r (%s)\n'
                '***  - incomplete email generated.\n'
                 % (refname, rev.type,)
                )
            klass = OtherReferenceChange

        return klass(
            environment,
            refname=refname, short_refname=short_refname,
            old=old, new=new, rev=rev,
            )

    def __init__(self, environment, refname, short_refname, old, new, rev):
        Change.__init__(self, environment)
        self.change_type = {
            (False, True) : 'create',
            (True, True) : 'update',
            (True, False) : 'delete',
            }[bool(old), bool(new)]
        self.refname = refname
        self.short_refname = short_refname
        self.old = old
        self.new = new
        self.rev = rev
        self.msgid = email.utils.make_msgid()
        self.diffopts = environment.diffopts

    def _compute_values(self):
        values = Change._compute_values(self)

        values['change_type'] = self.change_type
        values['refname_type'] = self.refname_type
        values['refname'] = self.refname
        values['short_refname'] = self.short_refname
        values['msgid'] = self.msgid
        values['recipients'] = self.recipients
        values['oldrev'] = str(self.old)
        values['oldrev_short'] = self.old.short
        values['newrev'] = str(self.new)
        values['newrev_short'] = self.new.short

        if self.old:
            values['oldrev_type'] = self.old.type
        if self.new:
            values['newrev_type'] = self.new.type
        return values

    def generate_email_header(self):
        return self.expand_lines(HEADER_TEMPLATE)

    def generate_email_body(self, push):
        """Call the appropriate body-generation routine.

        Call one of generate_create_summary() /
        generate_update_summary() / generate_delete_summary()."""

        change_summary = {
            'create' : self.generate_create_summary,
            'delete' : self.generate_delete_summary,
            'update' : self.generate_update_summary,
            }[self.change_type](push)
        for line in change_summary:
            yield line

        for line in self.generate_revision_change_summary(push):
            yield line

    def generate_email_footer(self):
        return self.expand_lines(FOOTER_TEMPLATE)

    def generate_revision_change_summary(self, push):
        """Generate a summary of the revisions added/removed by this change."""

        if self.new.commit and not self.old.commit:
            # A new reference was created.  List the new revisions
            # brought by the new reference (i.e., those revisions that
            # were not in the repository before this reference
            # change).
            sha1s = list(push.get_new_commits(self))
            sha1s.reverse()
            tot = len(sha1s)
            new_revisions = [
                Revision(self, GitObject(sha1), num=i+1, tot=tot)
                for (i, sha1) in enumerate(sha1s)
                ]

            if new_revisions:
                yield self.expand('This %(refname_type)s includes the following new commits:\n')
                yield '\n'
                for r in new_revisions:
                    yield '       new  %s\n' % (
                        iter(read_log_oneline('--max-count=1', r.rev.sha1)).next(),
                        )
                yield '\n'
                for line in self.expand_lines(NEW_REVISIONS_TEMPLATE, tot=tot):
                    yield line
            else:
                for line in self.expand_lines(NO_NEW_REVISIONS_TEMPLATE):
                    yield line

        elif self.new.commit and self.old.commit:
            # A reference was changed to point at a different commit.
            # List the revisions that were removed and/or added *from
            # that reference* by this reference change, along with a
            # diff between the trees for its old and new values.

            # List of the revisions that were added to the branch by
            # this update.  Note this list can include revisions that
            # have already had notification emails; we want such
            # revisions in the summary even though we will not send
            # new notification emails for them.
            adds = list(read_log_oneline(
                    '--topo-order', '--reverse', '%s..%s'
                    % (self.old.commit, self.new.commit,)
                    ))

            # List of the revisions that were removed from the branch
            # by this update.  This will be empty except for
            # non-fast-forward updates.
            discards = list(read_log_oneline(
                    '%s..%s' % (self.new.commit, self.old.commit,)
                    ))

            if adds:
                new_commits = CommitSet(push.get_new_commits(self))
            else:
                new_commits = CommitSet([])

            if discards:
                discarded_commits = CommitSet(push.get_discarded_commits(self))
            else:
                discarded_commits = CommitSet([])

            if discards and adds:
                for line in discards:
                    if line.split(' ', 1)[0] in discarded_commits:
                        yield '  discards  %s\n' % (line,)
                    else:
                        yield '     omits  %s\n' % (line,)
                for line in adds:
                    if line.split(' ', 1)[0] in new_commits:
                        yield '       new  %s\n' % (line,)
                    else:
                        yield '      adds  %s\n' % (line,)
                yield '\n'
                for line in self.expand_lines(NON_FF_TEMPLATE):
                    yield line

            elif discards:
                for line in discards:
                    if line.split(' ', 1)[0] in discarded_commits:
                        yield '  discards  %s\n' % (line,)
                    else:
                        yield '     omits  %s\n' % (line,)
                yield '\n'
                for line in self.expand_lines(REWIND_ONLY_TEMPLATE):
                    yield line

            elif adds:
                yield '      from  %s\n' % (
                    iter(read_log_oneline('--max-count=1', self.old.sha1)).next(),
                    )
                for line in adds:
                    if line.split(' ', 1)[0] in new_commits:
                        yield '       new  %s\n' % (line,)
                    else:
                        yield '      adds  %s\n' % (line,)

            yield '\n'

            if new_commits:
                for line in self.expand_lines(NEW_REVISIONS_TEMPLATE, tot=len(new_commits)):
                    yield line
            else:
                for line in self.expand_lines(NO_NEW_REVISIONS_TEMPLATE):
                    yield line

            # The diffstat is shown from the old revision to the new
            # revision.  This is to show the truth of what happened in
            # this change.  There's no point showing the stat from the
            # base to the new revision because the base is effectively a
            # random revision at this point - the user will be interested
            # in what this revision changed - including the undoing of
            # previous revisions in the case of non-fast-forward updates.
            yield '\n'
            yield 'Summary of changes:\n'
            for line in read_lines(
                ['git', 'diff-tree']
                + self.diffopts
                + ['%s..%s' % (self.old.commit, self.new.commit,)],
                keepends=True,
                ):
                yield line

        elif self.old.commit and not self.new.commit:
            # A reference was deleted.  List the revisions that were
            # removed from the repository by this reference change.

            sha1s = list(push.get_discarded_commits(self))
            tot = len(sha1s)
            discarded_revisions = [
                Revision(self, GitObject(sha1), num=i+1, tot=tot)
                for (i, sha1) in enumerate(sha1s)
                ]

            if discarded_revisions:
                for line in self.expand_lines(DISCARDED_REVISIONS_TEMPLATE):
                    yield line
                yield '\n'
                for r in discarded_revisions:
                    yield '  discards  %s\n' % (
                        iter(read_log_oneline('--max-count=1', r.rev.sha1)).next(),
                        )
            else:
                for line in self.expand_lines(NO_DISCARDED_REVISIONS_TEMPLATE):
                    yield line

        elif not self.old.commit and not self.new.commit:
            for line in self.expand_lines(NON_COMMIT_UPDATE_TEMPLATE):
                yield line

    def generate_create_summary(self, push):
        """Called for the creation of a reference."""

        # This is a new reference and so oldrev is not valid
        yield '        at  %s\n' % (
            iter(read_log_oneline('--max-count=1', self.new.sha1)).next(),
            )
        yield '\n'

    def generate_update_summary(self, push):
        """Called for the change of a pre-existing branch."""

        return iter([])

    def generate_delete_summary(self, push):
        """Called for the deletion of any type of reference."""

        yield '       was  %s\n' % (
            iter(read_log_oneline('--max-count=1', self.old.sha1)).next(),
            )
        yield '\n'


class BranchChange(ReferenceChange):
    refname_type = 'branch'

    def __init__(self, environment, refname, short_refname, old, new, rev):
        ReferenceChange.__init__(
            self, environment,
            refname=refname, short_refname=short_refname,
            old=old, new=new, rev=rev,
            )
        self.recipients = environment.get_refchange_recipients(self)


class AnnotatedTagChange(ReferenceChange):
    refname_type = 'annotated tag'

    def __init__(self, environment, refname, short_refname, old, new, rev):
        ReferenceChange.__init__(
            self, environment,
            refname=refname, short_refname=short_refname,
            old=old, new=new, rev=rev,
            )
        self.recipients = environment.get_announce_recipients(self)
        self.show_shortlog = environment.announce_show_shortlog

    ANNOTATED_TAG_FORMAT = (
        '%(*objectname)\n'
        '%(*objecttype)\n'
        '%(taggername)\n'
        '%(taggerdate)'
        )

    def describe_tag(self, push):
        """Describe the new value of an annotated tag."""

        # Use git for-each-ref to pull out the individual fields from
        # the tag
        [tagobject, tagtype, tagger, tagged] = read_lines(
            ['git', 'for-each-ref', '--format=%s' % (self.ANNOTATED_TAG_FORMAT,), self.refname],
            )

        yield '   tagging  %s (%s)\n' % (tagobject, tagtype)
        if tagtype == 'commit':
            # If the tagged object is a commit, then we assume this is a
            # release, and so we calculate which tag this tag is
            # replacing
            try:
                prevtag = read_output(['git', 'describe', '--abbrev=0', '%s^' % (self.new,)])
            except CommandError:
                prevtag = None
            if prevtag:
                yield '  replaces  %s\n' % (prevtag,)
        else:
            prevtag = None
            yield '    length  %s bytes\n' % (read_output(['git', 'cat-file', '-s', tagobject]),)

        yield ' tagged by  %s\n' % (tagger,)
        yield '        on  %s\n' % (tagged,)
        yield '\n'

        # Show the content of the tag message; this might contain a
        # change log or release notes so is worth displaying.
        yield LOGBEGIN
        contents = list(read_lines(['git', 'cat-file', 'tag', self.new.sha1], keepends=True))
        contents = contents[contents.index('\n') + 1:]
        if contents and contents[-1][-1:] != '\n':
            contents.append('\n')
        for line in contents:
            yield line

        if self.show_shortlog and tagtype == 'commit':
            # Only commit tags make sense to have rev-list operations
            # performed on them
            yield '\n'
            if prevtag:
                # Show changes since the previous release
                revlist = read_output(
                    ['git', 'rev-list', '--pretty=short', '%s..%s' % (prevtag, self.new,)],
                    keepends=True,
                    )
            else:
                # No previous tag, show all the changes since time
                # began
                revlist = read_output(
                    ['git', 'rev-list', '--pretty=short', '%s' % (self.new,)],
                    keepends=True,
                    )
            for line in read_lines(['git', 'shortlog'], input=revlist, keepends=True):
                yield line

        yield LOGEND
        yield '\n'

    def generate_create_summary(self, push):
        """Called for the creation of an annotated tag."""

        for line in self.expand_lines(TAG_CREATED_TEMPLATE):
            yield line

        for line in self.describe_tag(push):
            yield line

    def generate_update_summary(self, push):
        """Called for the update of an annotated tag.

        This is probably a rare event and may not even be allowed."""

        for line in self.expand_lines(TAG_UPDATED_TEMPLATE):
            yield line

        for line in self.describe_tag(push):
            yield line

    def generate_delete_summary(self, push):
        """Called when a non-annotated reference is updated."""

        for line in self.expand_lines(TAG_DELETED_TEMPLATE):
            yield line

        yield self.expand('   tag was  %(oldrev_short)s\n')
        yield '\n'


class NonAnnotatedTagChange(ReferenceChange):
    refname_type = 'tag'

    def __init__(self, environment, refname, short_refname, old, new, rev):
        ReferenceChange.__init__(
            self, environment,
            refname=refname, short_refname=short_refname,
            old=old, new=new, rev=rev,
            )
        self.recipients = environment.get_refchange_recipients(self)

    def generate_create_summary(self, push):
        """Called for the creation of an annotated tag."""

        for line in self.expand_lines(TAG_CREATED_TEMPLATE):
            yield line

    def generate_update_summary(self, push):
        """Called when a non-annotated reference is updated."""

        for line in self.expand_lines(TAG_UPDATED_TEMPLATE):
            yield line

    def generate_delete_summary(self, push):
        """Called when a non-annotated reference is updated."""

        for line in self.expand_lines(TAG_DELETED_TEMPLATE):
            yield line

        for line in ReferenceChange.generate_delete_summary(self, push):
            yield line


class OtherReferenceChange(ReferenceChange):
    refname_type = 'reference'

    def __init__(self, environment, refname, short_refname, old, new, rev):
        # We use the full refname as short_refname, because otherwise
        # the full name of the reference would not be obvious from the
        # text of the email.
        ReferenceChange.__init__(
            self, environment,
            refname=refname, short_refname=refname,
            old=old, new=new, rev=rev,
            )
        self.recipients = environment.get_refchange_recipients(self)


class Mailer(object):
    """An object that can send emails."""

    def send(self, lines):
        """Send an email consisting of lines.

        lines must be an iterable over the lines constituting the
        header and body of the email.  The recipients will be read
        from the email header."""

        raise NotImplementedError()


class SendMailer(Mailer):
    """Send emails using '/usr/sbin/sendmail -t'."""

    def __init__(self, envelopesender=None):
        self.envelopesender = envelopesender

    def send(self, lines):
        cmd = ['/usr/sbin/sendmail', '-t']
        if self.envelopesender:
            cmd.extend(['-f', self.envelopesender])
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            p.stdin.writelines(lines)
        except:
            sys.stderr.write(
                '*** Error while generating commit email\n'
                '***  - mail sending aborted.\n'
                )
            p.terminate()
            raise
        else:
            p.stdin.close()
            retcode = p.wait()
            if retcode:
                raise CommandError(cmd, retcode)


class OutputMailer(Mailer):
    """Write emails to an output stream, bracketed by lines of '=' characters.

    This is intended for debugging purposes."""

    SEPARATOR = '=' * 75 + '\n'

    def __init__(self, f):
        self.f = f

    def send(self, lines):
        self.f.write(self.SEPARATOR)
        self.f.writelines(lines)
        self.f.write(self.SEPARATOR)


# Set GIT_DIR either from the working directory, or based on the
# GIT_DIR environment variable:
try:
    GIT_DIR = read_output(['git', 'rev-parse', '--git-dir'])
except CommandError:
    sys.stderr.write('fatal: post-receive: not in a git working copy\n')
    sys.exit(1)


class UnknownUserError(Exception):
    pass


class Environment(object):
    """Describes the environment in which the push is occurring.

    An Environment object encapsulates information about the local
    environment.  For example, it knows how to determine:

    * the name of the repository to which the push occurred

    * what user did the push

    * what users want to be informed about various types of changes.

    An Environment object is expected to have the following attributes:

        repo_shortname

            A short name for the repository, for display purposes.

        emailprefix

            A string that will be prefixed to every email's subject.

        projectdesc

            A one-line description of the project.

        pusher

            The username of the person who pushed the changes.  If
            This value is used in the email body to indicate who
            pushed the change.

        pusher_email (may be None)

            The email address of the person who pushed the changes.
            The value should be a single RFC 2822 email address as a
            string; e.g., "Joe User <user@example.com>" if available,
            otherwise "user@example.com".  If set, the value is used
            as the Reply-To address for refchange emails.  If it is
            impossible to determine the pusher's email, this attribute
            should be set to None (in which case no Reply-To header
            will be output).

        sender

            The 'From' email address.

        administrator

            The name and/or email of the repository administrator.
            This value is used in the footer as the person to whom
            requests to be removed from the notification list should
            be sent.  Ideally, it should include a valid email
            address.

        announce_show_shortlog (bool)

            True iff announce emails should include a shortlog.

        diffopts (list of strings)

            The options that should be passed to 'git diff' for the
            summary email.  The value should be a list of strings
            representing words to be passed to the command.

    Additionally, the default implementation of filter_body() expects
    the following:

        maxlines (int or None)

            The maximum number of lines that should be included in an
            email.  If this value is set and is not None or zero, then
            truncate emails at this length and append a line
            indicating how many more lines were discarded).

        maxlinelength (int or None)

            The maximum length of any single line in the email body.
            Longer lines are truncated at that length with ' [...]'
            appended.

        strict_utf8 (bool)

            If this field is set to True, then the email body text is
            expected to be UTF-8.  Any invalid characters are
            converted to U+FFFD, the Unicode replacement character
            (encoded as UTF-8, of course).

    """

    VALUE_KEYS = [
        'repo_shortname',
        'projectdesc',
        'administrator',
        'emailprefix',
        'sender',
        'pusher',
        'pusher_email',
        ]

    def __init__(self):
        self.administrator = 'the administrator of this repository'
        self.emailprefix = ''

        try:
            self.projectdesc = open(os.path.join(GIT_DIR, 'description')).readline().strip()
            if not self.projectdesc or self.projectdesc.startswith('Unnamed repository'):
                self.projectdesc = 'UNNAMED PROJECT'
        except IOError:
            self.projectdesc = 'UNNAMED PROJECT'

        self.announce_show_shortlog = False
        self.maxlines = None
        self.maxlinelength = 500
        self.strict_utf8 = True
        self.diffopts = ['--stat', '--summary', '--find-copies-harder']

        self._values = None

    def get_values(self):
        """Return a dictionary {keyword : expansion} for this Environment.

        This method is called by Change._compute_values().  The keys
        in the returned dictionary are available to be used in any of
        the templates.  The dictionary is created by reading from self
        the attributes named in VALUE_KEYS that are set and not None.
        The return value is always a new dictionary."""

        if self._values is None:
            values = {}
            for key in self.VALUE_KEYS:
                value = getattr(self, key, None)
                if value is not None:
                    values[key] = value
            self._values = values

        return self._values.copy()

    def get_refchange_recipients(self, refchange):
        """Return the recipients for notifications about refchange.

        Return the list of email addresses to which notifications
        about the specified ReferenceChange should be sent."""

        raise NotImplementedError()

    def get_announce_recipients(self, annotated_tag_change):
        """Return the recipients for notifications about annotated_tag_change.

        Return the list of email addresses to which notifications
        about the specified AnnotatedTagChange should be sent."""

        raise NotImplementedError()

    def get_revision_recipients(self, revision):
        """Return the recipients for messages about revision.

        Return the list of email addresses to which notifications
        about the specified Revision should be sent.  This method
        could be overridden, for example, to take into account the
        contents of the revision when deciding whom to notify about
        it.  For example, there could be a scheme for users to express
        interest in particular files or subdirectories, and only
        receive notification emails for revisions that affecting those
        files."""

        raise NotImplementedError()

    def filter_body(self, lines):
        """Filter the lines intended for an email body.

        lines is an iterable over the lines that would go into the
        email body.  Filter it (e.g., limit the number of lines, the
        line length, character set, etc.), returning another iterable.
        By default, handle self.maxlines, self.maxlinelength, and
        self.strict_utf8 as described above."""

        if self.strict_utf8:
            lines = (line.decode('utf-8', 'replace') for line in lines)
            # Limit the line length in Unicode-space to avoid
            # splitting characters:
            if self.maxlinelength:
                lines = limit_linelength(lines, self.maxlinelength)
            lines = (line.encode('utf-8', 'replace') for line in lines)
        elif self.maxlinelength:
            lines = limit_linelength(lines, self.maxlinelength)

        if self.maxlines:
            lines = limit_lines(lines, self.maxlines)

        return lines


class ConfigEnvironment(Environment):
    """An Environment that reads most of its information from "git config"."""

    def __init__(self, config, repo_shortname, pusher, recipients=None):
        Environment.__init__(self)
        self.config = config

        # If there is a config setting, it overrides the constructor parameter:
        self.repo_shortname = self.config.get('reponame', default=repo_shortname)

        self.recipients = recipients
        self.emaildomain = self.config.get('emaildomain')

        if self.emaildomain:
            # Derive the pusher's full email address, and use it for
            # both pusher and pusher_email.
            self.pusher = self.pusher_email = '%s@%s' % (pusher, self.emaildomain)
        else:
            # We can't derive the pusher's email address, so use the
            # naked username as pusher and set pusher_email to None.
            self.pusher = pusher
            self.pusher_email = None

        # The recipients for various types of notification emails, as
        # RFC 2822 email addresses separated by commas (or the empty
        # string if no recipients are configured).  Although there is
        # a mechanism to choose the recipient lists based on on the
        # actual *contents* of the change being reported, we only
        # choose based on the *type* of the change.  Therefore we can
        # compute them once and for all:
        self._refchange_recipients = self._get_recipients('refchangelist', 'mailinglist')
        self._announce_recipients = self._get_recipients(
            'announcelist', 'refchangelist', 'mailinglist'
            )
        self._revision_recipients = self._get_recipients('commitlist', 'mailinglist')
        self.announce_show_shortlog = self.config.get_bool(
            'announceshortlog', default=self.announce_show_shortlog
            )
        self.sender = self.config.get('envelopesender', default=None)
        self.administrator = (
            self.config.get('administrator')
            or self.administrator
            )

        emailprefix = self.config.get('emailprefix', default=None)
        if emailprefix and emailprefix.strip():
            self.emailprefix = emailprefix.strip() + ' '
        else:
            self.emailprefix = '[%s]' % (self.repo_shortname,)

        maxlines = self.config.get('emailmaxlines', default=None)
        if maxlines is not None:
            self.maxlines = int(maxlines)

        maxlinelength = self.config.get('emailmaxlinelength', default=None)
        if maxlinelength is not None:
            self.maxlinelength = int(maxlinelength)

        strict_utf8 = self.config.get_bool('emailstrictutf8', default=None)
        if strict_utf8 is not None:
            self.strict_utf8 = strict_utf8

        diffopts = self.config.get('diffopts', None)
        if diffopts is not None:
            self.diffopts = diffopts.split()

    def _get_recipients(self, *names):
        """Return the recipients for a particular type of message.

        Return the list of email addresses to which a particular type
        of notification email should be sent, by looking at the config
        value for "multimailhook.$name" for each of names.  Use the
        value from the first name that is configured.  The return
        value is a (possibly empty) string containing RFC 2822 email
        addresses separated by commas.  If no configuration could be
        found, raise a ConfigurationException."""

        if self.recipients is not None:
            # The constructor argument (if any) trumps all others.
            return self.recipients
        for name in names:
            retval = self.config.get_recipients(name)
            if retval is not None:
                return retval
        if len(names) == 1:
            hint = 'Please set "%s.%s"' % (self.config.section, name)
        else:
            hint = (
                'Please set one of the following:\n    "%s"'
                % ('"\n    "'.join('%s.%s' % (self.config.section, name) for name in names))
                )

        raise ConfigurationException(
            'The list of recipients for %s is not configured.\n%s' % (names[0], hint)
            )

    def get_refchange_recipients(self, refchange):
        return self._refchange_recipients

    def get_announce_recipients(self, annotated_tag_change):
        return self._announce_recipients

    def get_revision_recipients(self, revision):
        return self._revision_recipients


class GenericEnvironment(ConfigEnvironment):
    REPO_NAME_RE = re.compile(r'^(?P<name>.+?)(?:\.git)?$')

    def __init__(self, config, recipients=None):
        ConfigEnvironment.__init__(
            self, config,
            repo_shortname=self._compute_repo_shortname(),
            pusher=os.environ.get('USER', 'unknown user'),
            recipients=recipients,
            )

    def _compute_repo_shortname(self):
        if read_output(['git', 'rev-parse', '--is-bare-repository']) == 'true':
            path = GIT_DIR
        else:
            try:
                path = read_output(['git', 'rev-parse', '--show-toplevel'])
            except CommandError:
                return 'unknown repository'

        basename = os.path.basename(os.path.abspath(path))
        m = self.REPO_NAME_RE.match(basename)
        if m:
            return m.group('name')
        else:
            return 'unknown repository'


class GitoliteEnvironment(ConfigEnvironment):
    def __init__(self, config, recipients=None):
        ConfigEnvironment.__init__(
            self, config,
            repo_shortname=os.environ.get('GL_REPO', 'unknown repository'),
            pusher=os.environ.get('GL_USER', 'unknown user'),
            recipients=recipients,
            )


class Push(object):
    """Represent an entire push (i.e., a group of ReferenceChanges).

    It is easy to figure out what commits were added to a *branch* by
    a Reference change:

        git rev-list change.old..change.new

    or removed from a *branch*:

        git rev-list change.new..change.old

    But it is not quite so trivial to determine which entirely new
    commits were added to the *repository* by a push and which old
    commits were discarded by a push.  A big part of the job of this
    class is to figure out these things, and to make sure that new
    commits are only detailed once even if they were added to multiple
    references.

    The first step is to determine the "other" references--those
    unaffected by the current push.  They are computed by
    Push._compute_other_refs() by listing all references then removing
    any affected by this push.

    The commits contained in the repository before this push were

        git rev-list other1 other2 other3 ... change1.old change2.old ...

    Where "changeN.old" is the old value of one of the references
    affected by this push.

    The commits contained in the repository after this push are

        git rev-list other1 other2 other3 ... change1.new change2.new ...

    The commits added by this push are the difference between these
    two sets, which can be written

        git rev-list \
            ^other1 ^other2 ... \
            ^change1.old ^change2.old ... \
            change1.new change2.new ...

    The commits removed by this push can be computed by

        git rev-list \
            ^other1 ^other2 ... \
            ^change1.new ^change2.new ... \
            change1.old change2.old ...

    The last point is that it is possible that other pushes are
    occurring simultaneously to this one, so reference values can
    change at any time.  It is impossible to eliminate all race
    conditions, but we reduce the window of time during which problems
    can occur by translating reference names to SHA1s as soon as
    possible and working with SHA1s thereafter (because SHA1s are
    immutable)."""

    # A map {(changeclass, changetype) : integer} specifying the order
    # that reference changes will be processed if multiple reference
    # changes are included in a single push.  The order is significant
    # mostly because new commit notifications are threaded together
    # with the first reference change that includes the commit.  The
    # following order thus causes commits to be grouped with branch
    # changes (as opposed to tag changes) if possible.
    SORT_ORDER = dict(
        (value, i) for (i, value) in enumerate([
            (BranchChange, 'update'),
            (BranchChange, 'create'),
            (AnnotatedTagChange, 'update'),
            (AnnotatedTagChange, 'create'),
            (NonAnnotatedTagChange, 'update'),
            (NonAnnotatedTagChange, 'create'),
            (BranchChange, 'delete'),
            (AnnotatedTagChange, 'delete'),
            (NonAnnotatedTagChange, 'delete'),
            (OtherReferenceChange, 'update'),
            (OtherReferenceChange, 'create'),
            (OtherReferenceChange, 'delete'),
            ])
        )

    def __init__(self, changes):
        self.changes = sorted(changes, key=self._sort_key)

        # The GitObjects referred to by references unaffected by this push:
        other_refs = self._compute_other_refs()

        self._old_rev_exclusion_spec = self._compute_rev_exclusion_spec(
            other_refs.union(change.old for change in self.changes)
            )
        self._new_rev_exclusion_spec = self._compute_rev_exclusion_spec(
            other_refs.union(change.new for change in self.changes)
            )

    @classmethod
    def _sort_key(klass, change):
        return (klass.SORT_ORDER[change.__class__, change.change_type], change.refname,)

    def _compute_other_refs(self):
        """Return the GitObjects referred to by references unaffected by this push."""

        # The refnames being changed by this push:
        updated_refs = set(
            change.refname
            for change in self.changes
            )

        # The GitObjects referred to by all references in this
        # repository *except* updated_refs:
        all_refs = set()
        for line in read_lines(['git', 'for-each-ref']):
            (sha1, type, name) = line.split()
            if name not in updated_refs:
                all_refs.add(GitObject(sha1, type))

        return all_refs

    def _compute_rev_exclusion_spec(self, git_objects):
        """Return an exclusion specification for 'git rev-list'.

        git_objects is an iterable over GitObject instances.  Return a
        string that can be passed to the standard input of 'git
        rev-list --stdin' to exclude all of the commits referred to by
        git_objects."""

        sha1s = set(
            git_object.sha1
            for git_object in git_objects
            if git_object and git_object.type in ['commit', 'tag']
            )

        return ''.join(
            ['^%s\n' % (sha1,) for sha1 in sorted(sha1s)]
            )

    def get_new_commits(self, reference_change=None):
        """Return a list of commits added by this push.

        Return a list of the object names of commits that were added
        by the part of this push represented by reference_change.  If
        reference_change is None, then return a list of *all* commits
        added by this push."""

        if not reference_change:
            new_revs = sorted(
                change.new.sha1
                for change in self.changes
                if change.new
                )
        elif not reference_change.new.commit:
            return []
        else:
            new_revs = [reference_change.new.commit.sha1]

        cmd = ['git', 'rev-list', '--stdin'] + new_revs
        return read_lines(cmd, input=self._old_rev_exclusion_spec)

    def get_discarded_commits(self, reference_change):
        """Return a list of commits discarded by this push.

        Return a list of the object names of commits that were
        entirely discarded from the repository by the part of this
        push represented by reference_change."""

        if not reference_change.old.commit:
            return []
        else:
            old_revs = [reference_change.old.commit.sha1]

        cmd = ['git', 'rev-list', '--stdin'] + old_revs
        return read_lines(cmd, input=self._new_rev_exclusion_spec)

    def send_emails(self, mailer, body_filter=None):
        """Use send all of the notification emails needed for this push.

        Use send all of the notification emails (including reference
        change emails and commit emails) needed for this push.  Send
        the emails using mailer.  If body_filter is not None, then use
        it to filter the lines that are intended for the email
        body."""

        # The sha1s of commits that were introduced by this push.
        # They will be removed from this set as they are processed, to
        # guarantee that one (and only one) email is generated for
        # each new commit.
        unhandled_sha1s = set(self.get_new_commits())
        for change in self.changes:
            # Check if we've got anyone to send to
            if not change.recipients:
                sys.stderr.write(
                    '*** no recipients configured so no email will be sent\n'
                    '*** for %r update %s->%s\n'
                    % (change.refname, change.old.sha1, change.new.sha1,)
                    )
            else:
                sys.stderr.write('Sending notification emails to: %s\n' % (change.recipients,))
                mailer.send(change.generate_email(self, body_filter))

            sha1s = []
            for sha1 in reversed(list(self.get_new_commits(change))):
                if sha1 in unhandled_sha1s:
                    sha1s.append(sha1)
                    unhandled_sha1s.remove(sha1)
            for (num, sha1) in enumerate(sha1s):
                rev = Revision(change, GitObject(sha1), num=num+1, tot=len(sha1s))
                if rev.recipients:
                    mailer.send(rev.generate_email(self, body_filter))

        # Consistency check:
        if unhandled_sha1s:
            sys.stderr.write(
                'ERROR: No emails were sent for the following new commits:\n'
                '    %s\n'
                % ('\n    '.join(sorted(unhandled_sha1s)),)
                )


def run_as_post_receive_hook(environment, mailer):
    changes = []
    for line in sys.stdin:
        (oldrev, newrev, refname) = line.strip().split(' ', 2)
        changes.append(
            ReferenceChange.create(environment, oldrev, newrev, refname)
            )
    push = Push(changes)
    push.send_emails(mailer, body_filter=environment.filter_body)


def run_as_update_hook(environment, mailer, refname, oldrev, newrev):
    changes = [
        ReferenceChange.create(
            environment,
            read_output(['git', 'rev-parse', '--verify', oldrev]),
            read_output(['git', 'rev-parse', '--verify', newrev]),
            refname,
            ),
        ]
    push = Push(changes)
    push.send_emails(mailer, body_filter=environment.filter_body)


KNOWN_ENVIRONMENTS = {
    'generic' : GenericEnvironment,
    'gitolite' : GitoliteEnvironment,
    }


def main(args):
    parser = optparse.OptionParser(
        description=__doc__,
        usage='%prog [OPTIONS]',
        )

    parser.add_option(
        '--environment', '--env', action='store', type='choice',
        choices=['generic', 'gitolite'], default=None,
        help=(
            'Choose type of environment is in use.  Default is taken from '
            'multimailhook.environment if set; otherwise "generic".'
            ),
        )
    parser.add_option(
        '--stdout', action='store_true', default=False,
        help='Output emails to stdout rather than sending them.',
        )
    parser.add_option(
        '--recipients', action='store', default=None,
        help='Set list of email recipients for all types of emails.',
        )

    (options, args) = parser.parse_args(args)

    config = Config('multimailhook')
    env = options.environment or config.get('environment', default=None)
    if not env:
        if 'GL_USER' in os.environ and 'GL_REPO' in os.environ:
            env = 'gitolite'
        else:
            env = 'generic'

    try:
        environment = KNOWN_ENVIRONMENTS[env](config, recipients=options.recipients)

        if options.stdout:
            mailer = OutputMailer(sys.stdout)
        else:
            mailer = SendMailer(environment.sender)

        # Dual mode: if arguments were specified on the command line, run
        # like an update hook; otherwise, run as a post-receive hook.
        if args:
            if len(args) != 3:
                parser.error('Need zero or three arguments')
            (refname, oldrev, newrev) = args
            run_as_update_hook(environment, mailer, refname, oldrev, newrev)
        else:
            run_as_post_receive_hook(environment, mailer)
    except ConfigurationException, e:
        sys.exit(str(e))


if __name__ == '__main__':
    main(sys.argv[1:])

