from ansible.module_utils.basic import AnsibleModule
import json
import urllib
import urllib.request as urllib2
import base64
import ssl


def influx_query(hostname, query, module_auth, module):
   ctx = ssl.create_default_context()
   ctx.check_hostname = False
   ctx.verify_mode = ssl.CERT_NONE

   url = 'https://' + hostname + ':8086/query'
   request = urllib2.Request(url=url, data=urllib.urlencode({'q': query}))
   if module_auth == 'true':
       base64string = base64.b64encode(
                         '%s:%s' % ('admin', 'YEajfEduiStEPYsY8hrj')
                      )
       request.add_header("Authorization", "Basic %s" % base64string)

   try:
       return urllib2.urlopen(request, context=ctx)
   except:
       module.fail_json(
           msg='Failed to query influxdb: \
           URL={} QUERY={}'.format(url, query)
       )


def check_module_changed(
    module,
    hostname,
    query,
    reference_param,
    error_message,
    module_auth
        ):

    return_code = True

    response = influx_query(hostname, query, module_auth, module)

    if response.getcode() != 200:
        module.fail_json(
            msg='%s: %s\n' %
            (
                error_message,
                response.read())
            )

    response_object = json.loads(response.read())
    series_object = response_object['results'][0]['series'][0]

    if 'values' in series_object.keys():
        objects = series_object['values']

        for entry in objects:
            if entry[0] == reference_param:
                return_code = False
                break

    return return_code, response.read()


def database_action(module, hostname, database_name, action, module_auth):

    moduleChanged, response_str = check_module_changed(
        module,
        hostname,
        "SHOW DATABASES",
        database_name,
        "error while querying db list",
        module_auth
        )

    if (moduleChanged):
        if action == 'present':
            query = '''
            CREATE DATABASE "{database}";
            CREATE RETENTION POLICY rp_1_year ON "{database}"
            DURATION 365d REPLICATION 1 DEFAULT;
            '''.format(database=database_name)
        else:
            query = '''
            DROP DATABASE "{database}";
            '''.format(database=database_name)

        response = influx_query(hostname, query, module_auth, module)
        response_body = response.read()

        if response.getcode() != 200:
            module.fail_json(
                msg='error in database_action: %s\n' %
                response.read()
                )

    module.exit_json(
        changed=moduleChanged,
        msg=response_str
        )


def main():
    argument_spec = dict(
        hostname=dict(required=True),
        database_name=dict(required=False),
        database_state=dict(
            required=False,
            choices=['present', 'absent'],
            default='present'
            ),
        username=dict(required=False),
        password=dict(required=False),
        admin=dict(
            required=False,
            choices=['true', 'false'],
            default='false'
            ),
        allow_database=dict(required=False),
        module_auth=dict(
            required=True,
            choices=['true', 'false'],
            )
        )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True
        )

    moduleChanged = True
    hostname = module.params['hostname']
    module_auth = module.params['module_auth']

    if module.params['admin'] == 'true':

        username = module.params['username']
        password = module.params['password']

        moduleChanged, response_str = check_module_changed(
            module,
            hostname,
            "SHOW USERS",
            username,
            "error while querying user list",
            module_auth
            )

        if moduleChanged:
            query = '''
            CREATE USER {username} WITH PASSWORD '{password}'
            WITH ALL PRIVILEGES
            '''.format(
                username=username,
                password=password
                )
            response = influx_query(hostname, query, module_auth, module)

            if response.getcode() != 200:
                module.fail_json(
                    msg='error creating admin user: %s\n' %
                    response.read()
                    )

        module.exit_json(
                changed=moduleChanged,
                msg=response_str
            )

    elif module.params['database_name']:

        database_action(
            module,
            hostname,
            module.params['database_name'],
            module.params['database_state'],
            module_auth
            )

    else:

        username = module.params['username']
        password = module.params['password']

        if module.params['allow_database']:
            allow_database = module.params['allow_database']

            moduleChanged, response_str = check_module_changed(
                module,
                hostname,
                "SHOW USERS",
                username,
                "error while querying user list",
                module_auth
                )

            query = '''
                CREATE USER {user} WITH PASSWORD '{pw}';
                GRANT ALL on "{db}" to "{user}";
                '''.format(
                    user=username,
                    pw=password,
                    db=allow_database
                    )

            response = influx_query(hostname, query, module_auth, module)
# unexpected influx query result without response.read()
            response_body = response.read()

            if response.getcode() != 200:
                module.fail_json(
                    msg='''
                    error executing query: {query}\nresponse: {resp}\n
                    '''.format(
                        query=query,
                        resp=response_body
                        )
                    )

            module.exit_json(
                changed=moduleChanged
            )

        else:
            module.fail_json(
                msg='''allow_database parameter required
                when creating non-admin user
                '''
            )


if __name__ == "__main__":
    main()
