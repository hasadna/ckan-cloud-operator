import traceback

from ckan_cloud_operator import logs

import ckan_cloud_operator.routers.routes.manager as routes_manager


def _get_base_static_config(**kwargs):
    logs.info('Generating base Traefik v2 static configuration', **kwargs)
    return dict({
        # 'debug': False,
        # 'log': {
        #     'level': 'DEBUG'
        # },
        # 'api': {
        #     'dashboard': True,
        #     'insecure': True
        # },
        # 'defaultEntryPoints': ['http'],
        'entryPoints': {
            'http': {
                'address': ':80'
            }
        },
        'ping': {
            'entryPoint': 'http'
        },
    }, **kwargs)


# def _get_acme_domains(domains, wildcard_ssl_domain=None, external_domains=False):
#     for root_domain, sub_domains in domains.items():
#         if external_domains:
#             for sub_domain in sub_domains:
#                 yield {'main': f'{sub_domain}.{root_domain}'}
#         elif root_domain == wildcard_ssl_domain:
#             yield {
#                 'main': f'*.{root_domain}',
#             }
#         else:
#             yield {
#                 'main': root_domain,
#                 'sans': [f'{sub_domain}.{root_domain}' for sub_domain in sub_domains]
#             }


def _add_letsencrypt(dns_provider, static_config, letsencrypt_cloudflare_email, wildcard_ssl_domain=None, external_domains=False, acme_email=None, routes=None):
    logs.info('Adding Letsencrypt acme Traefik v2 static configuration', dns_provider=dns_provider,
              letsencrypt_cloudflare_email=letsencrypt_cloudflare_email,
              wildcard_ssl_domain=wildcard_ssl_domain, external_domains=external_domains)
    assert dns_provider in ['route53', 'cloudflare', 'azure']
    # config['defaultEntryPoints'].append('https')
    static_config['entryPoints']['https'] = {
        'address': ':443',
    }
    # config['acme'] = {
    #     'email': letsencrypt_cloudflare_email,
    #     'storage': '/traefik-acme/acme.json',
    #     'entryPoint': 'https',
    #     **(
    #         {
    #             'tlsChallenge': {}
    #         } if external_domains else {
    #             'dnsChallenge': {
    #                 'provider': dns_provider
    #             }
    #         }
    #     ),
    #     'domains': list(_get_acme_domains(domains, wildcard_ssl_domain=wildcard_ssl_domain,
    #                                       external_domains=external_domains))
    # }
    if not acme_email:
        acme_email = letsencrypt_cloudflare_email
    assert '@' in acme_email, "invalid acme_email: %s" % acme_email
    static_config['certificatesResolvers'] = {
        'myresolver': {
            'acme': {
                'email': acme_email,
                'storage': '/traefik-acme/acme.json',
                **(
                    {
                        'tlsChallenge': {}
                    } if external_domains else {
                        'dnsChallenge': {
                            'provider': dns_provider
                        }
                    }
                ),
            }
        }
    }
    has_extra_external_domains = False
    for route in routes:
        if route['spec'].get('extra-external-domains'):
            has_extra_external_domains = True
            break
    if has_extra_external_domains:
        static_config['certificatesResolvers'] = {
            'tlsresolver': {
                'acme': {
                    'email': acme_email,
                    'storage': '/traefik-acme/acme-tls.json',
                    'tlsChallenge': {},
                }
            }
        }


def _add_route(dynamic_config, domains, route, enable_ssl_redirect, external_domains, wildcard_ssl_domain):
    route_name = routes_manager.get_name(route)
    logs.info(f'adding route to traefik v2 dynamic config: {route_name}')
    logs.debug_verbose(dynamic_config=dynamic_config, domains=domains, route=route, enable_ssl_redirect=enable_ssl_redirect)
    backend_url = routes_manager.get_backend_url(route)
    frontend_hostname = routes_manager.get_frontend_hostname(route)
    print(f'F/B = {frontend_hostname} {backend_url}')
    root_domain, sub_domain = routes_manager.get_domain_parts(route)
    domains.setdefault(root_domain, []).append(sub_domain)
    if route['spec'].get('extra-no-dns-subdomains'):
        extra_hostnames = ',' + ','.join([f'{s}.{root_domain}' for s in route['spec']['extra-no-dns-subdomains']])
    else:
        extra_hostnames = ''
    logs.debug_verbose(route_name=route_name, backend_url=backend_url, frontend_hostname=frontend_hostname, root_domain=root_domain,
                       sub_domain=sub_domain, domains=domains, extra_hostnames=extra_hostnames)
    if backend_url:
        # config['backends'][route_name] = {
        #     'servers': {
        #         'server1': {
        #             'url': backend_url
        #         }
        #     }
        # }
        dynamic_config['http']['services'][route_name] = {
            'loadBalancer': {
                'servers': [
                    {'url': backend_url}
                ]
            }
        }
        # config['frontends'][route_name] = {
        #     'backend': route_name,
        #     'passHostHeader': True,
        #     'headers': {
        #         'SSLRedirect': bool(enable_ssl_redirect)
        #     },
        #     'routes': {
        #         'route1': {
        #             'rule': f'Host:{frontend_hostname}{extra_hostnames}'
        #         }
        #     },
        #     **({
        #         'auth': {
        #             'basic': {
        #                 'usersFile': '/httpauth-' + route['spec']['httpauth-secret'] + '/.htpasswd'
        #             }
        #         }
        #     } if route['spec'].get('httpauth-secret') else {}),
        # }
        assert not extra_hostnames, "extra_hostnames not supported yet for traefik v2: %s" % extra_hostnames
        assert not route['spec'].get('httpauth-secret'), "httpauth-secret not supported yet for traefik v2: %s" % route['spec']['httpauth-secret']
        # passHostHeader is true by default
        dynamic_config['http']['routers']['http-%s' % route_name] = {
            'rule': f'Host(`{frontend_hostname}`)',
            'service': route_name,
            'middlewares': ['SSLRedirect'],
            'entrypoints': ['http'],
        }
        domain_confs = []
        assert not external_domains, "external_domains not yet supported for traefik v2"
        if root_domain == wildcard_ssl_domain:
            domain_confs.append({
                "main": f'*.{root_domain}'
            })
        else:
            domain_confs.append({
                "main": root_domain,
                'sans': [f'{sub_domain}.{root_domain}']
            })
        dynamic_config['http']['routers']['https-%s' % route_name] = {
            'rule': f'Host(`{frontend_hostname}`)',
            'service': route_name,
            'middlewares': [],
            'entrypoints': ['https'],
            'tls': {
                'certResolver': 'myresolver',
                'domains': domain_confs
            }
        }
        for i, domain in enumerate(route['spec'].get('extra-external-domains', [])):
            dynamic_config['http']['routers']['http-%s-eed%s' % (route_name, i)] = {
                'rule': f'Host(`{domain}`)',
                'service': route_name,
                'middlewares': ['SSLRedirect'],
                'entrypoints': ['http'],
            }
            dynamic_config['http']['routers']['https-%s-eed%s' % (route_name, i)] = {
                'rule': f'Host(`{domain}`)',
                'service': route_name,
                'middlewares': [],
                'entrypoints': ['https'],
                'tls': {
                    'certResolver': 'tlsresolver',
                    'domains': [{"main": domain}]
                }
            }


def get_static(routes, letsencrypt_cloudflare_email, enable_access_log=False, wildcard_ssl_domain=None, external_domains=False, dns_provider=None, acme_email=None, dynamic_config_file=None):
    if not dns_provider:
        dns_provider = 'cloudflare'
    assert dynamic_config_file, "missing dynamic_config_file"
    logs.info('Generating traefik v2 static configuration', routes_len=len(routes) if routes else 0,
              letsencrypt_cloudflare_email=letsencrypt_cloudflare_email, enable_access_log=enable_access_log,
              wildcard_ssl_domain=wildcard_ssl_domain, external_domains=external_domains)
    static_config = _get_base_static_config(
        providers={
            "file": {
                "watch": False,
                "filename": dynamic_config_file
            }
        },
        **(
            {
                'accessLog': {
                    "format": "json",
                    "fields": {
                        'defaultMode': "keep"
                    }
                },
            }
            if enable_access_log else {}
        )
    )
    if (
        (dns_provider == 'cloudflare' and letsencrypt_cloudflare_email)
        or (dns_provider == 'route53')
        or (dns_provider == 'azure')
    ):
        _add_letsencrypt(dns_provider, static_config, letsencrypt_cloudflare_email, wildcard_ssl_domain=wildcard_ssl_domain, external_domains=external_domains, acme_email=acme_email, routes=routes)
    else:
        logs.info('No valid dns_provider, will not setup SSL', dns_provider=dns_provider)
    return static_config


def get_dynamic(routes, letsencrypt_cloudflare_email, wildcard_ssl_domain=None, external_domains=False, dns_provider=None, force=False):
    if not dns_provider:
        dns_provider = 'cloudflare'
    logs.info('Generating traefik v2 dynamic configuration', routes_len=len(routes) if routes else 0,
              letsencrypt_cloudflare_email=letsencrypt_cloudflare_email, wildcard_ssl_domain=wildcard_ssl_domain, external_domains=external_domains)
    dynamic_config = {
        'http': {
            'routers': {},
            'services': {},
            'middlewares': {
                'SSLRedirect': {
                    'redirectScheme': {
                        'scheme': 'https',
                        'permanent': True
                    }
                }
            }
        }
    }
    domains = {}
    if dns_provider == 'cloudflare' and letsencrypt_cloudflare_email:
        enable_ssl_redirect = True
    elif dns_provider == 'route53':
        enable_ssl_redirect = True
    elif dns_provider == 'azure':
        enable_ssl_redirect = True
    else:
        enable_ssl_redirect = False
    logs.info(enable_ssl_redirect=enable_ssl_redirect)
    logs.info('Adding routes')
    i = 0
    errors = 0
    for route in routes:
        try:
            _add_route(dynamic_config, domains, route, enable_ssl_redirect, external_domains, wildcard_ssl_domain)
            i += 1
        except Exception as e:
            if force:
                logs.error(traceback.format_exc())
                logs.error(str(e))
                errors += 1
            else:
                raise
    logs.info(f'Added {i} routes')
    if errors > 0:
        logs.warning(f'Encountered {errors} errors')
    return dynamic_config
