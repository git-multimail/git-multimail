#! /usr/bin/env python

import os
import sys
TEST_DIR = os.path.abspath(os.path.dirname(sys.argv[0]))
PROJ_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, os.path.join(PROJ_DIR, 'git-multimail'))

import git_multimail

git_multimail.Config.add_config_parameters('multimailhook.reponame=name<with>special&chars;.git')

# A template with HTML in it:
git_multimail.REVISION_INTRO_TEMPLATE = """\
<span style="color:#808080">This is an automated email from the git hooks/post-receive script.</span><br /><br />

<strong>%(pusher)s</strong> pushed a commit to %(refname_type)s %(short_refname)s
in repository %(repo_shortname)s.<br />

<a href="https://github.com/git-multimail/git-multimail/commit/%(newrev)s">View on GitHub</a>.

"""

git_multimail.COMBINED_INTRO_TEMPLATE = git_multimail.REVISION_INTRO_TEMPLATE

git_multimail.main(sys.argv[1:])
