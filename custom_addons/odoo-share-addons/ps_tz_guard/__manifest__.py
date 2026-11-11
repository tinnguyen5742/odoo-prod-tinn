{
    'name': 'Timezone Guard',
    'version': '19.0.0.1',
    'summary': 'Prevent crashes caused by timezones missing from the OS tzdata',
    'description': 'Remaps legacy timezone names and clears timezone values that cannot be resolved in the running container. Hardens the tz_offset computes so reading records never raises on unknown timezone values.',
    'author': 'Patsoft',
    'license': 'LGPL-3',
    'category': 'Patsoft/Base',
    'depends': ['base'],
    'application': False,
    'auto_install': True,
    'post_init_hook': 'post_init_hook',
}
