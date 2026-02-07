#!/bin/sh
# Wrapper around signal-cli that adds --trust-new-identities always
# This wrapper is pointed to by OpenClaw's cliPath config
exec /usr/local/bin/signal-cli --trust-new-identities always "$@"
