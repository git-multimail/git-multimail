#! /bin/sh

# To be ran from within the VM running gerrit

cd "${0%/*}" || exit 1

file=/opt/gerrit/etc/gerrit.config

git config --file "$file" hooks.path $(pwd)
git config --file "$file" hooks.refUpdatedHook git-multimail-wrapper.sh
# git config --file "$file" hooks.refUpdateHook git-multimail-wrapper.sh
