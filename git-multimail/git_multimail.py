#! /usr/bin/env python2

# Copyright (c) 2012 Michael Haggerty
# Derived from contrib/hooks/post-receive-email, which is
# Copyright (c) 2007 Andy Parkins
# and also includes contributions by other authors.

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

This is an automated email from the git hooks/post-receive script.

%(pusher)s add a commit to %(refname_type)s %(short_refname)s
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
    """Generate a one-line summary for each revision in revspec."""

    cmd = ['git', 'log', '--abbrev=10', '--format=%h %s'] + list(log_args)
    return read_lines(cmd)


def read_updates(f):
    """Iterate over (oldrev, newrev, refname) for updates read from f.

    Read from f, which is assumed to be the format passed to the git
    pre-receive and post-receive hooks.  Output (oldrev, newrev,
    refname) tuples for each update, where oldrev and newrev are SHA1s
    or ZEROS and refname is the name of the reference being updated."""

    for line in f:
        (oldrev, newrev, refname) = line.strip().split(' ', 2)
        yield (oldrev, newrev, refname)


def limit_lines(lines, max_lines):
    for (index, line) in enumerate(lines):
        if index < max_lines:
            yield line

    if index >= max_lines:
        yield '... %d lines suppressed ...\n' % (index + 1 - max_lines,)


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

    def __nonzero__(self):
        return bool(self.sha1)

    def __str__(self):
        return self.sha1 or ZEROS


class Change(object):
    def __init__(self, environment):
        self.environment = environment
        self._values = None

    def _compute_values(self):
        retval = dict(
            repo_shortname=self.environment.get_repo_shortname(),
            administrator=self.environment.get_administrator(),
            pusher=self.environment.get_pusher(),
            projectdesc=self.environment.get_projectdesc(),
            emailprefix=self.environment.get_emailprefix(),
            )
        if self.environment.get_envelopesender() is not None:
            retval.update(sender=self.environment.get_envelopesender())
        try:
            retval.update(pusher_email=self.environment.username_to_email(retval['pusher']))
        except UnknownUserError:
            pass
        return retval

    def get_values(self, **extra_values):
        if self._values is None:
            self._values = self._compute_values()
        if extra_values:
            values = self._values.copy()
            values.update(extra_values)
            return values
        else:
            return self._values

    def expand(self, template, **extra_values):
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

    def generate_email(self, push, maxlines=None):
        """Generate an email describing this change.

        Iterate over the lines (including the headers) of an email
        describing this change.  If maxlines is set, then limit the
        body of the email to approximately that many lines."""

        for line in self.generate_email_header():
            yield line

        body = self.generate_email_body(push)
        if maxlines:
            body = limit_lines(body, maxlines)
        for line in body:
            yield line

        for line in self.generate_email_footer():
            yield line


class Revision(Change):
    def __init__(self, environment, reference_change, rev, num, tot):
        Change.__init__(self, environment)
        self.reference_change = reference_change
        self.rev = rev
        self.change_type = self.reference_change.change_type
        self.refname = self.reference_change.refname
        self.num = num
        self.tot = tot
        self.recipients = self.environment.get_revision_recipients(self)

    def _compute_values(self):
        retval = Change._compute_values(self)

        # First line of commit message:
        try:
            oneline = read_output(
                ['git', 'log', '--format=%s', '--max-count=1', self.rev.sha1]
                )
        except CommandError:
            oneline = self.rev.sha1

        retval.update(
            rev=self.rev.sha1,
            rev_short=self.rev.short,
            change_type=self.change_type,
            refname=self.refname,
            short_refname=self.reference_change.short_refname,
            refname_type=self.reference_change.refname_type,
            reply_to_msgid=self.reference_change.msgid,
            num=self.num,
            tot=self.tot,
            recipients=self.recipients,
            oneline=oneline,
            )
        try:
            retval.update(author=self.environment.email_to_email(self.get_author_email()))
        except UnknownUserError:
            pass
        return retval

    def get_author_email(self):
        return read_output(['git', 'log', '--max-count=1', '--format=%ae', self.rev.sha1])

    def generate_email_header(self):
        return self.expand_lines(REVISION_HEADER_TEMPLATE)

    def generate_email_body(self, push):
        """Show this revision."""

        return read_lines(
            ['git', 'show', '--find-copies', '--stat', '--patch', self.rev.sha1],
            keepends=True,
            )

    def generate_email_footer(self):
        return self.expand_lines(REVISION_FOOTER_TEMPLATE)


class ReferenceChange(Change):
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
        self.diffopts = environment.get_diffopts()

    def _compute_values(self):
        retval = Change._compute_values(self)
        retval.update(
            change_type=self.change_type,
            refname_type=self.refname_type,
            refname=self.refname,
            short_refname=self.short_refname,
            msgid=self.msgid,
            recipients=self.recipients,
            oldrev=str(self.old),
            oldrev_short=self.old.short,
            newrev=str(self.new),
            newrev_short=self.new.short,
            )
        if self.old:
            retval.update(oldrev_type=self.old.type)
        if self.new:
            retval.update(newrev_type=self.new.type)
        return retval

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

        # Consider this:
        #   1 --- 2 --- O --- X --- 3 --- 4 --- N
        #
        # O is oldrev for refname
        # N is newrev for refname
        # X is a revision pointed to by some other ref, for which we may
        #   assume that an email has already been generated.
        # In this case we want to issue an email containing only revisions
        # 3, 4, and N.  Given (almost) by
        #
        #  git rev-list N ^O --not --all
        #
        # The reason for the "almost", is that the "--not --all" will take
        # precedence over the "N", and effectively will translate to
        #
        #  git rev-list N ^O ^X ^N
        #
        # So, we need to build up the list more carefully.  git rev-parse
        # will generate a list of revs that may be fed into git rev-list.
        # We can get it to make the "--not --all" part and then filter out
        # the "^N" with:
        #
        #  git rev-parse --not --all | grep -v N
        #
        # Then, using the --stdin switch to git rev-list we have effectively
        # manufactured
        #
        #  git rev-list N ^O ^X
        #
        # This leaves a problem when someone else updates the repository
        # while this script is running.  Their new value of the ref we're
        # working on would be included in the "--not --all" output; and as
        # our newrev would be an ancestor of that commit, it would exclude
        # all of our commits.  What we really want is to exclude the current
        # value of refname from the --not list, rather than N itself.  So:
        #
        #  git rev-parse --not --all | grep -v $(git rev-parse $refname)
        #
        # Get's us to something pretty safe (apart from the small time
        # between refname being read, and git rev-parse running - for that,
        # I give up)
        #
        #
        # Next problem, consider this:
        #   * --- B --- * --- O (oldrev)
        #          \
        #           * --- X --- * --- N (newrev)
        #
        # That is to say, there is no guarantee that oldrev is a strict
        # subset of newrev (it would have required a --force, but that's
        # allowed).  So, we can't simply say rev-list oldrev..newrev.
        # Instead we find the common base of the two revs and list from
        # there.
        #
        # As above, we need to take into account the presence of X; if
        # another branch is already in the repository and points at some of
        # the revisions that we are about to output - we don't want them.
        # The solution is as before: git rev-parse output filtered.
        #
        # Finally, tags: 1 --- 2 --- O --- T --- 3 --- 4 --- N
        #
        # Tags pushed into the repository generate nice shortlog emails that
        # summarise the commits between them and the previous tag.  However,
        # those emails don't include the full commit messages that we output
        # for a branch update.  Therefore we still want to output revisions
        # that have been output on a tag email.
        #
        # Luckily, git rev-parse includes just the tool.  Instead of using
        # "--all" we use "--branches"; this has the added benefit that
        # "remotes/" will be ignored as well.

        if self.new.commit and not self.old.commit:
            # A new reference was created.  List the new revisions
            # brought by the new reference (i.e., those revisions that
            # were not in the repository before this reference
            # change).
            sha1s = list(push.get_new_commits(self))
            sha1s.reverse()
            tot = len(sha1s)
            new_revisions = [
                Revision(
                    push.environment, self,
                    GitObject(sha1), num=i+1, tot=tot,
                    )
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
                Revision(
                    push.environment, self,
                    GitObject(sha1), num=i+1, tot=tot,
                    )
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
        self.recipients = environment.get_refchange_recipients()


class AnnotatedTagChange(ReferenceChange):
    refname_type = 'annotated tag'

    def __init__(self, environment, refname, short_refname, old, new, rev):
        ReferenceChange.__init__(
            self, environment,
            refname=refname, short_refname=short_refname,
            old=old, new=new, rev=rev,
            )
        self.recipients = environment.get_announce_recipients()
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
        self.recipients = environment.get_refchange_recipients()

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
    refname_type = 'other reference'

    def __init__(self, environment, refname, short_refname, old, new, rev):
        ReferenceChange.__init__(
            self, environment,
            refname=refname, short_refname=short_refname,
            old=old, new=new, rev=rev,
            )
        self.recipients = environment.get_refchange_recipients()


ref_re = re.compile(r'^refs\/(?P<area>[^\/]+)\/(?P<shortname>.*)$')


def get_change(environment, oldrev, newrev, refname):
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
    m = ref_re.match(refname)
    if m:
        area = m.group('area')
        short_refname = m.group('shortname')
    else:
        area = ''
        short_refname = refname

    if rev.type == 'tag':
        # Annotated tag:
        return AnnotatedTagChange(
            environment,
            refname=refname, short_refname=short_refname,
            old=old, new=new, rev=rev,
            )
    elif rev.type == 'commit':
        if area == 'tags':
            # Non-annotated tag:
            return NonAnnotatedTagChange(
                environment,
                refname=refname, short_refname=short_refname,
                old=old, new=new, rev=rev,
                )
        elif area == 'heads':
            # Branch:
            return BranchChange(
                environment,
                refname=refname, short_refname=short_refname,
                old=old, new=new, rev=rev,
                )
        elif area == 'remotes':
            # Tracking branch:
            sys.stderr.write(
                '*** Push-update of tracking branch %r\n'
                '***  - incomplete email generated.\n'
                 % (refname,)
                )
        else:
            # Some other reference namespace:
            sys.stderr.write(
                '*** Push-update of strange reference %r\n'
                '***  - incomplete email generated.\n'
                 % (refname,)
                )
    else:
        # Anything else (is there anything else?)
        sys.stderr.write(
            '*** Unknown type of update to %r (%s)\n'
            '***  - incomplete email generated.\n'
             % (refname, rev.type,)
            )

    # For the cases not handled explicitly above, generate an
    # OtherReferenceChange:
    return OtherReferenceChange(
        environment,
        refname=refname, short_refname=short_refname,
        old=old, new=new, rev=rev,
        )


class Mailer(object):
    def send(self, lines):
        raise NotImplementedError()


class SendMailer(Mailer):
    """Send emails using '/usr/sbin/sendmail -t'."""

    def __init__(self, environment):
        self.envelopesender = environment.get_envelopesender()

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

    def __init__(self, environment, f):
        self.f = f

    def send(self, lines):
        self.f.write('=' * 75 + '\n')
        self.f.writelines(lines)
        self.f.write('=' * 75 + '\n')


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
    def __init__(self, config, recipients=None):
        self.config = config
        self.recipients = recipients
        self.emaildomain = None
        # The recipients for various types of notification emails, as
        # RFC 2822 email addresses separated by commas (or the empty
        # string if no recipients are configured):
        self._refchange_recipients = self._get_recipients('refchangelist', 'mailinglist')
        self._announce_recipients = self._get_recipients(
            'announcelist', 'refchangelist', 'mailinglist'
            )
        self._revision_recipients = self._get_recipients('commitlist', 'mailinglist')
        self.announce_show_shortlog = self.config.get_bool('announceshortlog', default=False)

    def get_repo_shortname(self):
        """Return a short name for the repository, for display purposes."""

        raise NotImplementedError()

    def get_pusher(self):
        """Return the username of the person who pushed the changes."""

        raise NotImplementedError()

    def username_to_email(self, username):
        """Return the email address for the specified username.

        The return values should be a single RFC 2822 email address as
        a string.  Raise UnknownUserError on error."""

        if self.emaildomain is None:
            self.emaildomain = self.config.get('emaildomain') or 'localhost'

        return '%s@%s' % (username, self.emaildomain)

    def email_to_email(self, email):
        """(Possibly) convert a short email address into a full email address.

        email is a short email address, like 'user@example.com'.
        Convert it into the RFC 2822 email address that should be used
        in the email headers for commit messages, which might be of
        the long form 'Lou User <user@example.com>'.  Raise
        UnknownUserError if the user is unknown (i.e., if this email
        address should be skipped)."""

        # By default, just return the short form:
        return email

    def _get_recipients(self, *names):
        """Return the recipients for a particular type of message.

        Return the list of email addresses to which a particular type
        of notification email should be sent, by looking at the config
        value for "multimailhook.$name" for each of names.  The return
        value is a (possibly empty) string containing RFC 2822 email
        addresses separated by commas from the first name that was
        configured.  If no configuration could be found, raise a
        ConfigurationException."""

        if self.recipients is not None:
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

    def get_refchange_recipients(self):
        """Return the recipients for refchange messages."""

        return self._refchange_recipients

    def get_announce_recipients(self):
        """Return the recipients for announcement messages.

        Return the list of email addresses to which AnnotatedTagChange
        emails should be sent."""

        return self._announce_recipients

    def get_revision_recipients(self, revision):
        """Return the recipients for messages about the specified revision.

        This method could be overridden, for example, to take into
        account the contents of the revision when deciding whom to
        notify about it.  For example, there could be a scheme for
        users to express interest in particular files or
        subdirectories, and only receive notification emails for
        revisions that affecting those files."""

        return self._revision_recipients

    def get_envelopesender(self):
        """Return the 'From' email address."""

        return self.config.get('envelopesender', default=None)

    def get_administrator(self):
        """Return the name and/or email of the repository administrator."""

        return (
            self.config.get('administrator')
            or self.get_envelopesender()
            or 'the administrator of this repository.'
            )

    def get_emailprefix(self):
        """Return a string that will be prefixed to every subject."""

        retval = self.config.get('emailprefix', default=None)
        if retval is None:
            retval = '[%s] ' % (self.get_repo_shortname(),)
        elif retval and not retval.endswith(' '):
            retval += ' '
        return retval

    def get_maxlines(self):
        """Return the maximum number of lines that should be included in an email.

        If this value is set and is not zero, then truncate emails at
        this length and append a line indicating how many more lines
        were discarded)."""

        maxlines = self.config.get('emailmaxlines', default=None)
        if maxlines is not None:
            maxlines = int(maxlines)
        return maxlines

    def get_projectdesc(self):
        """Return a one-line description of the project."""

        try:
            projectdesc = open(os.path.join(GIT_DIR, 'description')).readline().strip()
        except IOError:
            projectdesc = None
        else:
            # Check if the description is unchanged from its default, and
            # shorten it to a more manageable length if it is
            if projectdesc.startswith('Unnamed repository'):
                projectdesc = None

        return projectdesc or 'UNNAMED PROJECT'

    def get_diffopts(self):
        """Return options to pass to 'git diff'.

        Return the options that should be passed to 'git diff' for the
        summary email.  The return value should be a list of strings
        representing words to be passed to the command."""

        return self.config.get(
            'diffopts',
            default='--stat --summary --find-copies-harder'
            ).split()


class GenericEnvironment(Environment):
    repo_name_re = re.compile(r'^(?P<name>.+?)(?:\.git)?$')

    def __init__(self, config, recipients=None):
        Environment.__init__(self, config, recipients=recipients)

    def get_repo_shortname(self):
        retval = self.config.get('reponame', default=None)
        if retval:
            return retval

        if read_output(['git', 'rev-parse', '--is-bare-repository']) == 'true':
            path = GIT_DIR
        else:
            try:
                path = read_output(['git', 'rev-parse', '--show-toplevel'])
            except CommandError:
                return 'unknown repository'

        basename = os.path.basename(os.path.abspath(path))
        m = self.repo_name_re.match(basename)
        if m:
            return m.group('name')
        else:
            return basename

    def get_pusher(self):
        return os.environ.get('USER', 'unknown user')


class GitoliteEnvironment(Environment):
    def __init__(self, config, recipients=None):
        Environment.__init__(self, config, recipients=recipients)

    def get_repo_shortname(self):
        retval = self.config.get('reponame', default=None)
        if retval:
            return retval
        else:
            return os.environ.get('GL_REPO', 'unknown repository')

    def get_pusher(self):
        return os.environ.get('GL_USER', 'unknown user')


class Push(object):
    """Represent an entire push (i.e., a group of ReferenceChanges)."""

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

    def __init__(self, environment, changes):
        self.environment = environment
        self.changes = sorted(changes, key=self._sort_key)

        # The set of refnames unaffected by this push:
        self.other_refs = self._compute_other_refs()

        self._old_rev_exclusion_spec = self._compute_old_rev_exclusion_spec()
        self._new_rev_exclusion_spec = self._compute_new_rev_exclusion_spec()

    @classmethod
    def _sort_key(klass, change):
        return (klass.SORT_ORDER[change.__class__, change.change_type], change.refname,)

    def _compute_other_refs(self):
        """Return the set of names of references unaffected by this push."""

        # The refnames of all references in this repository:
        all_refs = set(
            read_lines(['git', 'for-each-ref', '--format=%(refname)'])
            )
        # The refnames being changed by this push:
        updated_refs = set(
            change.refname
            for change in self.changes
            )
        return all_refs - updated_refs

    def _compute_old_rev_exclusion_spec(self):
        """Return a string that excludes old revisions from 'git rev-list' output.

        Return a string that can be passed to the standard input of
        'git rev-list --stdin' to exclude all of the commits that were
        in the repository before this push."""

        # The objects pointed to by the old values of the refs that
        # were updated.  (Some of these might not be commits, but that
        # doesn't bother 'git rev-list'):
        old_revs = set(
            change.old.sha1
            for change in self.changes
            if change.old
            )

        return ''.join(
            ['^%s\n' % (refname,) for refname in self.other_refs]
            + ['^%s\n' % (rev,) for rev in old_revs]
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

    def _compute_new_rev_exclusion_spec(self):
        """Return a string that excludes new revisions from 'git rev-list' output.

        Return a string that can be passed to the standard input of
        'git rev-list --stdin' to exclude all of the commits that are
        in the repository after this push."""

        # The objects pointed to by the old values of the refs that
        # were updated.  (Some of these might not be commits, but that
        # doesn't bother 'git rev-list'):
        new_revs = set(
            change.new.sha1
            for change in self.changes
            if change.new
            )

        return ''.join(
            ['^%s\n' % (refname,) for refname in self.other_refs]
            + ['^%s\n' % (rev,) for rev in new_revs]
            )

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

    def send_emails(self, mailer, maxlines=None):
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
                mailer.send(change.generate_email(self, maxlines))

            sha1s = []
            for sha1 in reversed(list(self.get_new_commits(change))):
                if sha1 in unhandled_sha1s:
                    sha1s.append(sha1)
                    unhandled_sha1s.remove(sha1)
            for (num, sha1) in enumerate(sha1s):
                rev = Revision(
                    self.environment, change,
                    GitObject(sha1), num=num+1, tot=len(sha1s),
                    )
                if rev.recipients:
                    mailer.send(rev.generate_email(self, maxlines))

        # Consistency check:
        if unhandled_sha1s:
            sys.stderr.write(
                'ERROR: No emails were sent for the following new commits:\n'
                '    %s\n'
                % ('\n    '.join(sorted(unhandled_sha1s)),)
                )


def run_as_post_receive_hook(environment, mailer):
    changes = [
        get_change(environment, oldrev, newrev, refname)
        for (oldrev, newrev, refname) in read_updates(sys.stdin)
        ]
    push = Push(environment, changes)
    push.send_emails(mailer, maxlines=environment.get_maxlines())


def run_as_update_hook(environment, mailer, refname, oldrev, newrev):
    changes = [
        get_change(
            environment,
            read_output(['git', 'rev-parse', '--verify', oldrev]),
            read_output(['git', 'rev-parse', '--verify', newrev]),
            refname,
            ),
        ]
    push = Push(environment, changes)
    push.send_emails(mailer, maxlines=environment.get_maxlines())


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
            mailer = OutputMailer(environment, sys.stdout)
        else:
            mailer = SendMailer(environment)

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

