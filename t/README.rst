Aids to testing git-multimail.

This directory contains some scripts that can be used to help test
git-multimail.  The tests are not very complete and not all of them are
automated, but they do catch many errors.

It is likely that the test scripts only work correctly on Linux/Unix,
and it is quite possible that they require a newer version of Python
than does the git-multimail script itself.

The testsuite uses Sharness_. Tests scripts are ``*.t`` files.

.. _Sharness: https://github.com/mlafeldt/sharness

Short instructions
==================

For an approximate test that you haven't broken anything, run::

    $ verbose=t make

, which runs all available tests.  The main test, test-email-content,
simulates the sending of many notification emails for a test
repository and compares the email texts with the expected results,
which are recorded in multimail.expect.  If this test shows any
discrepancies, then either

a. Your change broke something.  Fix it :-)

b. Your change intentionally improved something.  Make absolutely sure
   that you like the change, then copy the new output to
   multimail.expect, double-check that *now* the tests run without
   errors, then commit the new version of multimail.expect along with
   the rest of your change.


Test scripts
============

email-content.t:

    This is the main test script, it calls git_multimail.py in various
    conditions with --stdout, and checks that the output is the
    expected one. Expected output is stored in ``email-content.d/*``.

create-test-repo:

    Create a test repository "test-repo.git" that can be used for
    testing git-multimail.  Most of the repository is created by
    loading the dumpfile "test-repo.dump", then a few more weird tags
    are created that point to objects other than commits.

fake-sendmail:

    A shell script that is used by the test scripts as the "sendmail"
    command.  It simply writes the email text to its standard output
    along with information about how it was invoked, thereby
    preventing the sending of any actual emails.

filter-noise:

    Filters from the generate-test-emails output many strings that
    vary unpredictably from one test run to another to make it easier
    to compare the output of different runs.

generate-test-emails:

    **Warning:** The use of this file is deprecated. Use
    email-content.t instead.

    Runs create-test-repo and then simulates a bunch of pushes to the
    repository, writing to stdout the emails that would normally be
    sent for those pushes.  The output of this script can be filtered
    using filter-noise then compared against multimail.expect by
    running test-email-content.

test-env:

    Runs through various configuration scenarios for
    GenericEnvironment and GitoliteEnvironment and verifies that the
    environments have set the correct values for the
    template-expansion parameters.


Other files
===========

helper-functions.sh

    A set of shell functions and variables used by other scripts.

test-repo.dump

    A file that is read by create-test-repo (using "git fast-import")
    to create most of the test repository.

email-content.d/

    This directory contains the expected outputs of email-content.t,
    already filtered using filter-noise.  Please adjust these files if
    you make a change that intentionally alters the output of
    git-multimail.

$SHARNESS_TRASH_DIRECTORY/test-repo.git/

    Test repository created by create-test-repo and used for the
    test-email-content test.

$SHARNESS_TRASH_DIRECTORY/env-repo.git/

    Test repository created and used by test-env.  This directory is
    usually deleted automatically at the end of the test.
