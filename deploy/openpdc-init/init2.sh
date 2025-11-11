#!/bin/sh

_DB_NAME="openPDC"
_DB_USER="polito"
_DB_PASS="pass"
_DB_ROOTPASS=""
_DB_URL="localhost"
_DB_PORT="3306"

if test ! -z $DB_NAME
then
    _DB_NAME=$DB_NAME
fi

if test ! -z $DB_USER
then
    _DB_USER=$DB_USER
fi

if test ! -z $DB_PASS
then
    _DB_PASS=$DB_PASS
fi

if test ! -z $DB_ROOTPASS
then
    _DB_ROOTPASS=$DB_ROOTPASS
fi

if test ! -z $DB_URL
then
    _DB_URL=$DB_URL
fi

if test ! -z $DB_PORT
then
    _DB_PORT=$DB_PORT
fi


if mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} -e "use ${_DB_NAME}" 2> /dev/null
then
    echo "database already exists, skipping creation"
else
    echo "database ${_DB_NAME} does not exists at ${_DB_URL}:${_DB_PORT}"
    # generate new configuration
    sed 's/DB_NAME/'"${_DB_NAME}"'/;s/NewUser/'"${_DB_USER}"'/;s/MyPassword/'"${_DB_PASS}"'/' openPDC.sql.template > openPDC.sql
    sed 's/DB_NAME/'"${_DB_NAME}"'/' InitialDataSet.sql.template > InitialDataSet.sql
    sed 's/DB_NAME/'"${_DB_NAME}"'/' AuditLog.sql.template > AuditLog.sql
	
	
    echo "creating database and tables..."

    if mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} < openPDC.sql ; then : ; else
        return 10
    fi
    echo "done"
    echo "populating database with required data..."

    #mettere modifiche DB QUA!!!
	
    mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} -e "ALTER TABLE ${_DB_NAME}.ApplicationRoleSecurityGroup ADD c INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST;"
	mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} -e "ALTER TABLE ${_DB_NAME}.ApplicationRoleUserAccount ADD c INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST;"
	mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} -e "ALTER TABLE ${_DB_NAME}.ConfigurationEntity ADD c INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST;"
	mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} -e "ALTER TABLE ${_DB_NAME}.DataOperation ADD c INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST;"
	mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} -e "ALTER TABLE ${_DB_NAME}.ImportedMeasurement ADD c INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST;"
	mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} -e "ALTER TABLE ${_DB_NAME}.SecurityGroupUserAccount ADD c INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST;"
	
	
	if mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} < InitialDataSet.sql ; then : ; else
        return 10
    fi
    echo "done"
    echo "creating triggers..."
    if mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} < AuditLog.sql ; then : ; else
        return 10
    fi
    echo "done"

    if test "$SAMPLE_DATASET" = "true"
    then
        sed 's/DB_NAME/'"${_DB_NAME}"'/' SampleDataSet.sql.template > SampleDataSet.sql
        echo "populating database with sample dataset"
        if mysql --host=${_DB_URL} --port=${_DB_PORT} --user=root --password=${_DB_ROOTPASS} < SampleDataSet.sql ; then : ; else
            return 10
        fi
        echo "done"
    fi

    rm openPDC.sql
    _DB_PASS=""
    DB_PASS=""
fi
