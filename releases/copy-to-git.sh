#!/bin/bash

cd "${0%/*}"/.. || exit 1
. t/helper-functions.sh || exit 1

gitsrc="$1"

date=$(date  +'%B %d %Y')
sha1=$(git rev-list --no-walk HEAD)
tag=$(git tag --points-at HEAD)

if test -z "$gitsrc"
then
	fatal "Please, specify the path to the Git source tree as argument"
fi

if ! test -d "$gitsrc"
then
	fatal "not a directory: $gitsrc"
fi

if ! test -f "$gitsrc"/git.c
then
	fatal "cannot find file: $gitsrc/git.c.
Are you sure it's Git's source tree?"
fi

if test -z "$tag"
then
	fatal "Please, run this script on a tagged version"
fi

if test $(printf '%s\n' "$tags" | wc -l) -ne 1
then
	fatal "Please, run this script on a revision with only one tag"
fi

cp $(git ls-files git-multimail/) "$gitsrc"/contrib/hooks/multimail/
cd "$gitsrc"/contrib/hooks/multimail/
sed -e "s/@DATE@/$date/" -e "s/@SHA1@/$sha1 refs\/tags\/$tag/" README.Git.template \
	>README.Git
rm -f README.Git.template

git status .
