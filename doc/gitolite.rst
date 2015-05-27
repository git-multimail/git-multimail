Setting up git-multimail on gitolite
====================================

``git-multimail`` supports gitolite natively. Setting up
``git-multimail`` on a gitolite 3 installation can be done like this:

Set up the hook
---------------

Log in as your gitolite user.

Create a file ``.gitolite/hooks/common/post-receive`` on your gitolite
account containing (adapt the path, obviously)::

  #!/bin/sh
  exec /path/to/git-multimail/git-multimail/git_multimail.py "$@"

Make sure it's executable (``chmod +x``). Record the hook in
gitolite::

  gitolite setup


Configuration
-------------

First, you have to allow the admin to set Git configuration variables.

Edit the line containing ``GIT_CONFIG_KEYS`` in file ``.gitolite.rc``,
to make it look like::

  GIT_CONFIG_KEYS                 =>  'multimailhook\..*',

You can now log out and return to your normal user.

In the ``gitolite-admin`` clone, edit the file ``conf/gitolite.conf``
and add::

  repo @all
      # Not strictly needed as git_multimail.py will chose gitolite if
      # $GL_USER is set.
      config multimailhook.environment = gitolite
      config multimailhook.mailingList = # Where emails should be sent
      config multimailhook.from = # From address to use

Obviously, you can customize all parameters on a per-repository basis by
adding these ``config multimailhook.*`` lines in the section
corresponding to a repository or set of repositories.

To activate ``git-multimail`` on a per-repository basis, do not set
``multimailhook.mailingList`` in the ``@all`` section and set it only
for repositories for which you want ``git-multimail``.

Alternatively, you can set up the ``From:`` field on a per-user basis
by adding a ``BEGIN USER EMAILS``/``END USER EMAILS`` section (see
``../../README``).
