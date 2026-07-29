FROM python:3.13-alpine@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0 AS python-runtime

FROM scratch
COPY --from=python-runtime /lib /lib
COPY --from=python-runtime /usr/lib /usr/lib
COPY --from=python-runtime /usr/local /usr/local
COPY --chown=65532:65532 --chmod=0555 parse_cv.py /sandbox/parse_cv.py
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/python", "/sandbox/parse_cv.py"]
