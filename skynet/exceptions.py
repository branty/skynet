#  Copyright  2017 EasyStack, Inc


"""Exception definitions."""


class SkynetException(Exception):
    """The base exception class for all exceptions"""
    pass


class MappingFileNotFound(SkynetException):
    """Not find mapping.json"""
    pass


class LogConfigurationNotFound(SkynetException):
    """Error configuration about log file path"""
    pass


class PipelineException(SkynetException):
    def __init__(self, message, pipeline_cfg):
        self.msg = message
        self.pipeline_cfg = pipeline_cfg

    def __str__(self):
        return 'Pipeline %s: %s' % (self.pipeline_cfg, self.msg)


class PipelineFileNotFound(SkynetException):
    """Not found about skynet pipline file"""
    pass
