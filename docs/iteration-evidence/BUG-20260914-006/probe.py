def test_origin():
    import config
    print('config_origin=' + config.__file__)
    print('has_new_field=' + str('compact_successful_build' in config.Settings.model_fields))
