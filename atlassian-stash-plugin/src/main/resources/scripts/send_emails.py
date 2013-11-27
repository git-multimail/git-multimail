#! /usr/bin/env python2

import imp
import sys
git_multimail = imp.load_source('git_multimail', sys.argv[1])

### Change templates
#git_multimail.FOOTER_TEMPLATE = "Here is a link to an internal wiki page: http://local.net/about-commit-emails"
#git_multimail.REVISION_FOOTER_TEMPLATE = ""

### An example of tweaking core functionality
#def prefix_all_emails(self):
#  emailprefix = self.config.get('emailprefix')
#  if emailprefix and emailprefix.strip():
#    return emailprefix.strip() + ' '
#  else:
#    return '[YourEmailPrefix] %s ' % (self.get_repo_shortname(),)
#git_multimail.StashEnvironmentMixin.get_emailprefix = prefix_all_emails

# Just use git_multimail's default config, environments, and remaining
# templates as-is
git_multimail.main(sys.argv[2:])
