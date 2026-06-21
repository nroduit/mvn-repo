If ## Maven Repository ##

This is the Maven repository for third-party libraries not available in Maven Central. To use this repository maven add in your pom.xml:

``` xml
  <repositories>
    <repository>
      <snapshots>
        <enabled>true</enabled>
        <updatePolicy>daily</updatePolicy>
      </snapshots>
      <id>mvn-repo-master</id>
      <name>Master Maven Repository</name>
      <url>https://raw.githubusercontent.com/nroduit/mvn-repo/master/</url>
    </repository>
  </repositories>
```

Snapshots are enabled because some artifacts (e.g. `weasis-i18n-dist`) are rebuilt
regularly. They use the non-unique layout (a constant `-SNAPSHOT` filename), so each
version directory carries a `maven-metadata.xml` whose `lastUpdated` advances when the
artifact is rebuilt — that is what tells Maven to re-download it. Use `always` instead
of `daily` if a build must pick up a new snapshot the same day it is published.

## Maintaining the repository ##

After adding or removing artifacts, regenerate the `maven-metadata.xml` files and the
`.sha1`/`.md5` checksums by running:

``` sh
python3 update-repo.py            # add --dry-run to preview without writing
```

The script needs only Python 3 (no extra dependencies), runs from any directory, and
works the same on macOS and Linux. It only rewrites files whose content changed. It also
writes the per-version `maven-metadata.xml` for SNAPSHOT artifacts and bumps their
`lastUpdated` when the artifact changed, so a rebuilt snapshot must be followed by
`update-repo.py` + commit + push for consumers to pick it up.

The git history is periodically squashed to keep the repository small, which rewrites
`master` (force-push). After that a `git pull` will fail, so delete your local copy and
clone the repository again.
