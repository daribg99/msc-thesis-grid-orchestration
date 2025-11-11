FROM alpine:3.13

RUN \
  adduser -h /home/polito -s /sbin/nologin -u 1000 -D polito && \
  apk add --no-cache \
    dumb-init \
    mariadb-client 

COPY init.sh /home/polito/init.sh

COPY openPDC.sql.template /home/polito/openPDC.sql.template

COPY InitialDataSet.sql.template /home/polito/InitialDataSet.sql.template

COPY SampleDataSet.sql.template /home/polito/SampleDataSet.sql.template

COPY AuditLog.sql.template /home/polito/AuditLog.sql.template

RUN chmod +x /home/polito/init.sh

USER    polito
WORKDIR /home/polito
VOLUME  /home/polito

ENTRYPOINT [ "/usr/bin/dumb-init" ]
CMD [ "./init.sh" ]
