Testing gerrit is mostly manual, but this directory contains some
material to help.

* Download vagrant-gerrit from
  https://github.com/roidelapluie/vagrant-gerrit and checkout Git
  submodules.

* Get a copy/clone of git-multimail as a subdirectory of
  vagrant-gerrit.

* Start the VM: vagrant up

* Launch a shell: vagrant ssh -c 'sudo -s'. From this shell, run::

  /vagrant/git-multimail/t/gerrit/setup-gerrit-hooks.sh

* Play with gerrit, push to a ref

* The output of the hook should be in
  /tmp/git-multimail-wrapper-log.txt
