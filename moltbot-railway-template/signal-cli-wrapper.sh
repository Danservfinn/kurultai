#!/bin/sh
# Wrapper around signal-cli that adds --trust-new-identities always
# This wrapper is pointed to by OpenClaw's cliPath config
# Cap JVM heap to 256MB to prevent OOM in constrained Railway containers
export _JAVA_OPTIONS="-Xmx256m -XX:+UseSerialGC"
exec /usr/local/bin/signal-cli --trust-new-identities always "$@"
