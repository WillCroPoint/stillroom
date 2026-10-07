<!-- Maintainer: fill in the architecture, tested macOS versions and actual archive
name before publishing. Link the guide to this release tag rather than a moving
branch. Add real first-launch screenshots with absolute, tag-pinned image URLs;
do not publish placeholders. This file does not create or publish a release. -->

## macOS application

Stillroom includes Python and the image converter. No Python or Docker installation
is needed. Download the macOS application archive under **Assets**, rather than
GitHub's automatically generated **Source code** archives.

<!-- List the actual archive name, supported architecture and tested macOS versions. -->

### First launch

**This app is not signed with an Apple Developer ID or notarized by Apple.**
macOS will normally block its first launch after download.

1. Extract the archive and move **Stillroom.app** to **Applications**.
2. Try opening it once from Finder.
3. Open **System Settings → Privacy & Security → Open Anyway**, then confirm.

After this approval, subsequent launches normally work from Finder. No Terminal
commands or global disabling of macOS protections are required. Only approve a
copy downloaded from this repository; managed Macs may not permit an exception.

[Apple's illustrated first-launch instructions](https://support.apple.com/en-us/102445)

<!-- Add an absolute link to deploy/macos/README.md at this release tag, plus
one or two screenshots of the warning and Open Anyway button. -->
