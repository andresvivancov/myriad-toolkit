'''
Copyright 2010-2011 DIMA Research Group, TU Berlin

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
 
Created on Feb 25, 2012

@author: Alexander Alexandrov <alexander.alexandrov@tu-berlin.de>
'''

import logging
import os
import re

from myriad.compiler.ast import RandomSequenceNode
from myriad.compiler.ast import LiteralArgumentNode
from myriad.compiler.ast import ResolvedFunctionRefArgumentNode
from myriad.compiler.ast import ResolvedFieldRefArgumentNode
from myriad.compiler.ast import ResolvedDirectFieldRefArgumentNode
from myriad.compiler.ast import ResolvedRecordReferenceRefArgumentNode
from myriad.compiler.ast import ResolvedReferencedFieldRefArgumentNode
from myriad.compiler.ast import ResolvedHydratorRefArgumentNode
from myriad.compiler.ast import RecordEnumFieldNode
from myriad.compiler.ast import StringSetRefArgumentNode
from myriad.compiler.ast import DepthFirstNodeFilter
from myriad.compiler.ast import EnumSetNode
from myriad.compiler.ast import FunctionNode
from myriad.compiler.ast import CardinalityEstimatorNode
from myriad.util.stringutil import StringTransformer

class ArgumentTransformer(object):
    
    _log = logging.getLogger("source.transformer.factory")
    _descriptor_pattern = re.compile('^([a-zA-Z_]+)\(([a-zA-Z_\*]*)\)(\*)?$')
    
    def createTransformer(transformerDescriptor):
        m = ArgumentTransformer._descriptor_pattern.match(transformerDescriptor)
        if (m):
            transformerType = m.group(1)
            argTransformer = None
            argKey = m.group(2)
            argOptional = m.group(3) is not None 
            
            if (transformerType == "Literal"):
                argTransformer = LiteralTransfomer()
            elif (transformerType == "FieldSetter"):
                argTransformer = FieldSetterTransfomer()
            elif (transformerType == "FieldGetter"):
                argTransformer = FieldGetterTransfomer()
            elif (transformerType == "RandomSetInspector"):
                argTransformer = RandomSetInspectorTransfomer()
            elif (transformerType == "FunctionRef"):
                argTransformer = FunctionRefTransfomer()
            elif (transformerType == "EnvVariable"):
                argTransformer = EnvVariableTransfomer(varName=argKey)
                argKey = None
            else:
                message = "Unknown argument transformer type `%s`" % (transformerType)
                ArgumentTransformer._log.error(message)
                raise RuntimeError(message)
            
            return (argTransformer, argKey, argOptional)
        else:
            message = "Bad argument transformer descriptor `%s`" % (transformerDescriptor)
            ArgumentTransformer._log.error(message)
            raise RuntimeError(message)
        
    def compileConstructorArguments(self, argsContainerNode, env = {}):
        argsCode = []
        
        for transformerDescriptor in argsContainerNode.getConstructorArguments():
            (argTransformer, argKey, argOptional) = ArgumentTransformer.createTransformer(transformerDescriptor)
            
            if argKey is None:
                argument = None
            else:
                argument = argsContainerNode.getArgument(argKey)
            
            argsCode.append(argTransformer.transform(argument, env.get("config", "config"), argOptional))
        
        return filter(None, argsCode)
        
    # static methods
    createTransformer = staticmethod(createTransformer)
    compileConstructorArguments = staticmethod(compileConstructorArguments)


class FieldTransfomer(object):

    def __init__(self, *args, **kwargs):
        pass
    
    def transform(self, argumentNode = None, configVarName = "config", optional = False):
        raise RuntimeError("Called abstract method FieldTransfomer.transform()")


class LiteralTransfomer(object):
    
    _expr_pattern = re.compile('%(\([\w.\-]+\))?([\w.\-]+)%')    
    _param_pattern = re.compile('^\${(.+)}$')
    
    def __init__(self, *args, **kwargs):
        super(LiteralTransfomer, self).__init__()
    
    def transform(self, argumentNode = None, configVarName = "config", optional = False):
        if optional is True and argumentNode is None:
            return None
        
        if configVarName is not None:
            configPrefix = configVarName + "."
        else:
            configPrefix = ""
        
        if isinstance(argumentNode, LiteralArgumentNode):
            attributeType = argumentNode.getAttribute("type").strip()
            attributeValue = argumentNode.getAttribute("value").strip()
            
            m = self._expr_pattern.match(attributeValue)
            if (m):
                return '%sparameter<%s>("%s")' % (configPrefix, attributeType, m.group(2))
            
            m = self._param_pattern.match(attributeValue)
            if (m):
                exprExpandedParams = self._expr_pattern.sub(lambda m: '%sparameter<%s>("%s")' % (configPrefix, attributeType if m.group(1) == None else m.group(1)[1:-1], m.group(2)), attributeValue)
                return "static_cast<%s>(%s)" % (attributeType, exprExpandedParams[2:-1])
            else:
                if attributeType == "String":
                    return '"%s"' % (attributeValue)
                else:
                    return '%s' % (attributeValue)
        else:
            raise RuntimeError("Unsupported argument `%s` of type `%s`" % (argumentNode.getAttribute("key"), type(argumentNode)))


class FieldSetterTransfomer(object):
    def __init__(self, *args, **kwargs):
        super(FieldSetterTransfomer, self).__init__()
    
    def transform(self, argumentNode = None, configVarName = "config", optional = False):
        if optional is True and argumentNode is None:
            return None
        
        if isinstance(argumentNode, ResolvedDirectFieldRefArgumentNode):
            typeName = StringTransformer.us2ccAll(argumentNode.getRecordTypeRef().getAttribute("key"))
            fieldAccessMethodName = StringTransformer.us2cc(argumentNode.getFieldRef().getAttribute("name"))
            return '&%s::%s' % (typeName, fieldAccessMethodName)
        if isinstance(argumentNode, ResolvedRecordReferenceRefArgumentNode):
            typeName = StringTransformer.us2ccAll(argumentNode.getRecordTypeRef().getAttribute("key"))
            fieldAccessMethodName = StringTransformer.us2cc(argumentNode.getRecordReferenceRef().getAttribute("name"))
            return '&%s::%s' % (typeName, fieldAccessMethodName)
        else:
            raise RuntimeError("Unsupported argument `%s` of type `%s`" % (argumentNode.getAttribute("key"), type(argumentNode)))


class FieldGetterTransfomer(object):

    def __init__(self, *args, **kwargs):
        super(FieldGetterTransfomer, self).__init__()
    
    def transform(self, argumentNode = None, configVarName = "config", optional = False):
        if optional is True and argumentNode is None:
            return None
        
        if isinstance(argumentNode, ResolvedDirectFieldRefArgumentNode):
            recordTypeNameUS = argumentNode.getRecordTypeRef().getAttribute("key")
            recordTypeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(recordTypeNameUS))
            
            fieldNode = argumentNode.getFieldRef()
            fieldType = fieldNode.getAttribute("type")
            fieldName = fieldNode.getAttribute("name")
                
            return "new FieldGetter<%(t)s, %(f)s>(&%(t)s::%(m)s)" % {'t': recordTypeNameCC, 'f': StringTransformer.sourceType(fieldType), 'm': StringTransformer.us2cc(fieldName)}

        elif isinstance(argumentNode, ResolvedReferencedFieldRefArgumentNode):
            recordTypeNameUS = argumentNode.getRecordTypeRef().getAttribute("key")
            recordTypeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(recordTypeNameUS))
            
            referenceName = argumentNode.getRecordReferenceRef().getAttribute("name")
            referenceTypeNameUS = argumentNode.getRecordReferenceRef().getRecordTypeRef().getAttribute("key")
            referenceTypeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(referenceTypeNameUS))
            
            fieldNode = fieldArgumentNode.getFieldRef()
            fieldType = fieldNode.getAttribute("type")
            fieldName = fieldNode.getAttribute("name")

            return "new ReferencedRecordFieldGetter<%(t)s, %(r)s, %(f)s>(&%(t)s::%(l)s, &%(r)s::%(m)s)" % {'t': recordTypeNameCC, 'r': referenceTypeNameCC, 'f': StringTransformer.sourceType(fieldType), 'l': StringTransformer.us2cc(referenceName), 'm': StringTransformer.us2cc(fieldName)}
        
        else:
            raise RuntimeError("Unsupported argument `%s` of type `%s`" % (argumentNode.getAttribute("key"), type(argumentNode)))


class RandomSetInspectorTransfomer(object):
    def __init__(self, *args, **kwargs):
        super(RandomSetInspectorTransfomer, self).__init__()
    
    def transform(self, argumentNode = None, configVarName = "config", optional = False):
        if optional is True and argumentNode is None:
            return None
        
        if configVarName is not None:
            configPrefix = configVarName + "."
        else:
            configPrefix = ""
            
        if isinstance(argumentNode, ResolvedDirectFieldRefArgumentNode):
            typeName = StringTransformer.us2ccAll(argumentNode.getRecordTypeRef().getAttribute("key"))
            return '%sgeneratorPool().get<%sGenerator>().inspector()' % (configPrefix, typeName)
        if isinstance(argumentNode, ResolvedRecordReferenceRefArgumentNode):
            typeName = StringTransformer.us2ccAll(argumentNode.getRecordReferenceRef().getRecordTypeRef().getAttribute("key"))
            return '%sgeneratorPool().get<%sGenerator>().inspector()' % (configPrefix, typeName)
        else:
            raise RuntimeError("Unsupported argument `%s` of type `%s`" % (argumentNode.getAttribute("key"), type(argumentNode)))


class FunctionRefTransfomer(object):

    def __init__(self, *args, **kwargs):
        super(FunctionRefTransfomer, self).__init__()
    
    def transform(self, argumentNode = None, configVarName = "config", optional = False):
        if optional is True and argumentNode is None:
            return None
        
        if configVarName is not None:
            configPrefix = configVarName + "."
        else:
            configPrefix = ""
            
        if isinstance(argumentNode, ResolvedFunctionRefArgumentNode):
            functionType = argumentNode.getAttribute("concrete_type")
            functionName = argumentNode.getAttribute("ref")
            return '%sfunc< %s >("%s")' % (configPrefix, functionType, functionName)
        else:
            raise RuntimeError("Unsupported argument `%s` of type `%s`" % (argumentNode.getAttribute("key"), type(argumentNode)))


class EnvVariableTransfomer(object):
    
    __varName = None

    def __init__(self, *args, **kwargs):
        super(EnvVariableTransfomer, self).__init__()
        self.__varName = kwargs.get("varName")
    
    def transform(self, argumentNode = None, configVarName = "config", optional = False):
        return self.__varName


class SourceCompiler(object):
    '''
    An abstract compiler type for all C++ source compiler components. 
    '''
    
    BUFFER_SIZE = 512
    PARAM_PREFIX = 'generator.'
    
    _args = None
    _srcPath = None
    _dgenName = None
    
    _log = None
    
    def __init__(self, args):
        '''
        Constructor
        '''
        self._args = args
        self._srcPath = "%s/../../src" % (args.base_path)
        self._dgenName = args.dgen_name
        
        self._log = logging.getLogger("source.compiler")


class FrontendCompiler(SourceCompiler):
    '''
    classdocs
    '''
    
    def __init__(self, *args, **kwargs):
        '''
        Constructor
        '''
        super(FrontendCompiler, self).__init__(*args, **kwargs)
        
    def compile(self, astRoot):
        self._log.warning("compiling frontend C++ sources")
        self.compileMainMethod(astRoot)
            
    def compileMainMethod(self, astRoot):
        try:
            os.makedirs("%s/cpp/core" % (self._srcPath))
        except OSError:
            pass
        
        sourcePath = "%s/cpp/core/main.cpp" % (self._srcPath)
        
        if (not os.path.isfile(sourcePath)):
            wfile = open(sourcePath, "w", SourceCompiler.BUFFER_SIZE)
            
            print >> wfile, '#include "core/constants.h"'
            print >> wfile, '#include "core/Frontend.h"'
            print >> wfile, ''
            print >> wfile, 'namespace Myriad {'
            print >> wfile, ''
            print >> wfile, '/**'
            print >> wfile, ' * Application name.'
            print >> wfile, ' */'
            print >> wfile, 'const String Constant::APP_NAME = "%s - Parallel Data Generator";' % (self._args.dgen_name)
            print >> wfile, ''
            print >> wfile, '/**'
            print >> wfile, ' * Application version.'
            print >> wfile, ' */'
            print >> wfile, 'const String Constant::APP_VERSION = "0.1.0";'
            print >> wfile, ''
            print >> wfile, '} // Myriad namespace'
            print >> wfile, ''
            print >> wfile, '// define the application main method'
            print >> wfile, 'POCO_APP_MAIN(Myriad::Frontend)'
    
            wfile.close()


class GeneratorSubsystemCompiler(SourceCompiler):
    '''
    classdocs
    '''
    
    def __init__(self, *args, **kwargs):
        '''
        Constructor
        '''
        super(GeneratorSubsystemCompiler, self).__init__(*args, **kwargs)
        
    def compile(self, astRoot):
        self._log.warning("compiling generator subsystem C++ sources")
        self.compileBaseGeneratorSubsystem(astRoot)
        self.compileGeneratorSubsystem(astRoot)
            
    def compileBaseGeneratorSubsystem(self, astRoot):
        try:
            os.makedirs("%s/cpp/generator/base" % (self._srcPath))
        except OSError:
            pass
        
        wfile = open("%s/cpp/generator/base/BaseGeneratorSubsystem.h" % (self._srcPath), "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '// auto-generatad base generator config C++ file'
        print >> wfile, ''
        print >> wfile, '#ifndef BASEGENERATORSUBSYSTEM_H_'
        print >> wfile, '#define BASEGENERATORSUBSYSTEM_H_'
        print >> wfile, ''
        print >> wfile, '#include "generator/AbstractGeneratorSubsystem.h"'
        print >> wfile, ''
        print >> wfile, 'namespace Myriad {'
        print >> wfile, ''
        print >> wfile, 'class BaseGeneratorSubsystem: public AbstractGeneratorSubsystem'
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    BaseGeneratorSubsystem(NotificationCenter& notificationCenter, const vector<bool>& executeStages) : '
        print >> wfile, '        AbstractGeneratorSubsystem(notificationCenter, executeStages)'
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    virtual ~BaseGeneratorSubsystem()'
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, 'protected:'
        print >> wfile, ''
        print >> wfile, '    virtual void registerGenerators();'
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '} // namespace Myriad'
        print >> wfile, ''
        print >> wfile, '#endif /* BASEGENERATORSUBSYSTEM_H_ */'
        
        wfile.close()
        
        wfile = open("%s/cpp/generator/base/BaseGeneratorSubsystem.cpp" % (self._srcPath), "w", SourceCompiler.BUFFER_SIZE)

        print >> wfile, '// auto-generatad base generator config C++ file'
        print >> wfile, ''
        print >> wfile, '#include "generator/base/BaseGeneratorSubsystem.h"'
        
        for recordSequence in astRoot.getSpecification().getRecordSequences().getRecordSequences():
            print >> wfile, '#include "generator/%sGenerator.h"' % (StringTransformer.us2ccAll(recordSequence.getAttribute("key")))

        print >> wfile, ''
        print >> wfile, 'using namespace std;'
        print >> wfile, 'using namespace Poco;'
        print >> wfile, ''
        print >> wfile, 'namespace Myriad {'
        print >> wfile, ''
        print >> wfile, '// the initial stage ID should always be zero'
        print >> wfile, 'I32u RecordGenerator::Stage::NEXT_STAGE_ID = 0;'
        print >> wfile, ''
        print >> wfile, '// register the valid stages for the Myriad generator extension'
        print >> wfile, 'RecordGenerator::StageList initList()'
        print >> wfile, '{'
        print >> wfile, '    RecordGenerator::StageList tmp;'
        print >> wfile, ''
        
        for recordSequence in astRoot.getSpecification().getRecordSequences().getRecordSequences():
            print >> wfile, '    tmp.push_back(RecordGenerator::Stage("%s"));' % (recordSequence.getAttribute("key"))
        
        print >> wfile, ''
        print >> wfile, '    return tmp;'
        print >> wfile, '}'
        print >> wfile, ''
        print >> wfile, 'const RecordGenerator::StageList RecordGenerator::STAGES(initList());'
        print >> wfile, ''
        print >> wfile, '// register the record sequence generators'
        print >> wfile, 'void BaseGeneratorSubsystem::registerGenerators()'
        print >> wfile, '{'
        
        for recordSequence in astRoot.getSpecification().getRecordSequences().getRecordSequences():
            print >> wfile, '    registerGenerator<%s::%sGenerator>("%s");' % (self._args.dgen_ns, StringTransformer.us2ccAll(recordSequence.getAttribute("key")), recordSequence.getAttribute("key"))
            
        print >> wfile, '}'
        print >> wfile, ''
        print >> wfile, '} // namespace Myriad'
        
        wfile.close()
            
    def compileGeneratorSubsystem(self, astRoot):
        try:
            os.makedirs("%s/cpp/generator" % (self._srcPath))
        except OSError:
            pass
        
        sourceHeaderPath = "%s/cpp/generator/GeneratorSubsystem.h" % (self._srcPath)
        sourcePath = "%s/cpp/generator/GeneratorSubsystem.cpp" % (self._srcPath)
        
        if (not os.path.isfile(sourceHeaderPath)):
            wfile = open(sourceHeaderPath, "w", SourceCompiler.BUFFER_SIZE)
            
            print >> wfile, '#ifndef GENERATORSUBSYSTEM_H_'
            print >> wfile, '#define GENERATORSUBSYSTEM_H_'
            print >> wfile, ''
            print >> wfile, '#include "generator/base/BaseGeneratorSubsystem.h"'
            print >> wfile, ''
            print >> wfile, 'using namespace std;'
            print >> wfile, 'using namespace Poco;'
            print >> wfile, ''
            print >> wfile, 'namespace Myriad {'
            print >> wfile, ''
            print >> wfile, 'class GeneratorSubsystem : public BaseGeneratorSubsystem'
            print >> wfile, '{'
            print >> wfile, 'public:'
            print >> wfile, ''
            print >> wfile, '    GeneratorSubsystem(NotificationCenter& notificationCenter, const vector<bool>& executeStages) :'
            print >> wfile, '        BaseGeneratorSubsystem(notificationCenter, executeStages)'
            print >> wfile, '    {'
            print >> wfile, '    }'
            print >> wfile, ''
            print >> wfile, '    virtual ~GeneratorSubsystem()'
            print >> wfile, '    {'
            print >> wfile, '    }'
            print >> wfile, ''
            print >> wfile, 'protected:'
            print >> wfile, ''
            print >> wfile, '    virtual void registerGenerators();'
            print >> wfile, '};'
            print >> wfile, ''
            print >> wfile, '} // namespace Myriad'
            print >> wfile, ''
            print >> wfile, '#endif /* GENERATORSUBSYSTEM_H_ */'
    
            wfile.close()
        
        if (not os.path.isfile(sourcePath)):
            wfile = open(sourcePath, "w", SourceCompiler.BUFFER_SIZE)
            
            print >> wfile, '#include "generator/GeneratorSubsystem.h"'
            print >> wfile, ''
            print >> wfile, 'using namespace std;'
            print >> wfile, 'using namespace Poco;'
            print >> wfile, ''
            print >> wfile, 'namespace Myriad {'
            print >> wfile, ''
            print >> wfile, 'void GeneratorSubsystem::registerGenerators()'
            print >> wfile, '{'
            print >> wfile, '    BaseGeneratorSubsystem::registerGenerators();'
            print >> wfile, ''
            print >> wfile, '    // register generators with the autorelease pool'
            print >> wfile, '}'
            print >> wfile, ''
            print >> wfile, '} // namespace Myriad'
    
            wfile.close()
        

class ConfigCompiler(SourceCompiler):
    '''
    classdocs
    '''
    
    def __init__(self, *args, **kwargs):
        '''
        Constructor
        '''
        super(ConfigCompiler, self).__init__(*args, **kwargs)
        
    def compile(self, astRoot):
        self._log.warning("compiling generator config C++ sources")
        self.compileParameters(astRoot)
        self.compileBaseConfig(astRoot)
        self.compileConfig(astRoot)
            
    def compileParameters(self, astRoot):
        try:
            os.makedirs("%s/config" % (self._srcPath))
        except OSError:
            pass
        
        # we assume that the node config *.properties file already exists
        rfile = open("%s/config/%s-node.properties" % (self._srcPath, self._dgenName), "r", SourceCompiler.BUFFER_SIZE)
        lines = rfile.readlines()
        rfile.close()
        
        parameters = astRoot.getSpecification().getParameters().getAll()
        
        filteredLines = []

        for l in lines:
            l = l.strip()
            
            if len(l) == 0 or l[0] == '#':
                filteredLines.append(l)
                continue
            
            key = l[0:l.find("=")].strip()
            
            if not key.startswith(SourceCompiler.PARAM_PREFIX):
                filteredLines.append(l)
                continue
            
            key = key[len(SourceCompiler.PARAM_PREFIX):]
            
            if not parameters.has_key(key):
                filteredLines.append(l)
        
        wfile = open("%s/config/%s-node.properties" % (self._srcPath, self._dgenName), "w", SourceCompiler.BUFFER_SIZE)
        
        for l in filteredLines:
            print >> wfile, l
            
        for k, v in parameters.iteritems():
            print >> wfile, '%s%s = %s' % (SourceCompiler.PARAM_PREFIX, k, v)
        
        wfile.close()
            
    def compileBaseConfig(self, astRoot):
        try:
            os.makedirs("%s/cpp/config/base" % (self._srcPath))
        except OSError:
            pass
        
        wfile = open("%s/cpp/config/base/BaseGeneratorConfig.h" % (self._srcPath), "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '// auto-generatad base generator config C++ file'
        print >> wfile, ''
        print >> wfile, '#ifndef BASEGENERATORCONFIG_H_'
        print >> wfile, '#define BASEGENERATORCONFIG_H_'
        print >> wfile, ''
        print >> wfile, '#include "config/AbstractGeneratorConfig.h"'
        print >> wfile, ''
        print >> wfile, 'namespace Myriad {'
        print >> wfile, ''
        print >> wfile, 'class BaseGeneratorConfig: public AbstractGeneratorConfig'
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    BaseGeneratorConfig(GeneratorPool& generatorPool) : AbstractGeneratorConfig(generatorPool)'
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, 'protected:'
        print >> wfile, ''
        print >> wfile, '    virtual void configurePartitioning()'
        print >> wfile, '    {'
        print >> wfile, '        // TODO: this piece of auto-generating code / Config API needs to be rewritten'
        print >> wfile, ''


        literalTransformer = LiteralTransfomer()
        nodeFilter = DepthFirstNodeFilter(filterType=CardinalityEstimatorNode)
        for cardinalityEstimator in nodeFilter.getAll(astRoot.getSpecification().getRecordSequences()):
            cardinalityEstimatorType = cardinalityEstimator.getAttribute("type")
            
            if cardinalityEstimatorType == 'linear_scale_estimator':
                print >> wfile, '        // setup linear scale estimator for %s' % (cardinalityEstimator.getParent().getAttribute("key"))
                print >> wfile, '        setString("partitioning.%s.base-cardinality", toString<%s>(%s));' % (cardinalityEstimator.getParent().getAttribute("key"), cardinalityEstimator.getArgument("base_cardinality").getAttribute("type").strip(), literalTransformer.transform(cardinalityEstimator.getArgument("base_cardinality"), None))
                print >> wfile, '        computeLinearScalePartitioning("%s");' % (cardinalityEstimator.getParent().getAttribute("key"))
        
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    virtual void configureFunctions()'
        print >> wfile, '    {'
        print >> wfile, '        // register prototype functions'
        
        nodeFilter = DepthFirstNodeFilter(filterType=FunctionNode)
        for function in nodeFilter.getAll(astRoot.getSpecification().getFunctions()):
            argsCode = ArgumentTransformer.compileConstructorArguments(self, function, {'config': None})
            print >> wfile, '        addFunction(new %(t)s(%(a)s));' % {'t': function.getConcreteType(), 'a': ', '.join(argsCode)}

        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    virtual void configureSets()'
        print >> wfile, '    {'
        print >> wfile, '        // bind string sets to config members with the bindStringSet method'
        
        literalTransformer = LiteralTransfomer()
        nodeFilter = DepthFirstNodeFilter(filterType=EnumSetNode)
        for enumSet in nodeFilter.getAll(astRoot):
            print >> wfile, '        bindEnumSet("%(n)s", %(p)s);' % {'n': enumSet.getAttribute("key"), 'p': literalTransformer.transform(enumSet.getArgument("path"), None)}

        print >> wfile, '    }'
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '} // namespace Myriad'
        print >> wfile, ''
        print >> wfile, '#endif /* BASEGENERATORCONFIG_H_ */'
        
        wfile.close()
            
    def compileConfig(self, astRoot):
        try:
            os.makedirs("%s/cpp/config" % (self._srcPath))
        except OSError:
            pass
        
        sourcePath = "%s/cpp/config/GeneratorConfig.h" % (self._srcPath)
        
        if (os.path.isfile(sourcePath)):
            return
        
        wfile = open(sourcePath, "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '#ifndef GENERATORCONFIG_H_'
        print >> wfile, '#define GENERATORCONFIG_H_'
        print >> wfile, ''
        print >> wfile, '#include "config/base/BaseGeneratorConfig.h"'
        print >> wfile, ''
        print >> wfile, 'namespace Myriad {'
        print >> wfile, ''
        print >> wfile, 'class GeneratorConfig: public BaseGeneratorConfig'
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    GeneratorConfig(GeneratorPool& generatorPool) : BaseGeneratorConfig(generatorPool)'
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, 'protected:'
        print >> wfile, ''
        print >> wfile, '    virtual void configurePartitioning()'
        print >> wfile, '    {'
        print >> wfile, '        BaseGeneratorConfig::configurePartitioning();'
        print >> wfile, '        // override or add partitioning config here'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    virtual void configureFunctions()'
        print >> wfile, '    {'
        print >> wfile, '        BaseGeneratorConfig::configureFunctions();'
        print >> wfile, '        // override or add functions here'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    virtual void configureSets()'
        print >> wfile, '    {'
        print >> wfile, '        BaseGeneratorConfig::configureSets();'
        print >> wfile, '        // override or add enumerated sets here'
        print >> wfile, '    }'
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '} // namespace Myriad'
        print >> wfile, ''
        print >> wfile, '#endif /* GENERATORCONFIG_H_ */'

        wfile.close()


class OutputCollectorCompiler(SourceCompiler):
    '''
    classdocs
    '''
    
    def __init__(self, *args, **kwargs):
        '''
        Constructor
        '''
        super(OutputCollectorCompiler, self).__init__(*args, **kwargs)
        
    def compile(self, astRoot):
        self._log.warning("compiling output collector C++ sources")
        self.compileOutputCollector(astRoot)
            
    def compileOutputCollector(self, astRoot):
        try:
            os.makedirs("%s/cpp/io" % (self._srcPath))
        except OSError:
            pass
        
        sourcePath = "%s/cpp/io/OutputCollector.cpp" % (self._srcPath)
        
        if (not os.path.isfile(sourcePath)):
            wfile = open(sourcePath, "w", SourceCompiler.BUFFER_SIZE)
            
            print >> wfile, '#include "io/OutputCollector.h"'
            print >> wfile, '#include "record/Record.h"'
            print >> wfile, ''
            print >> wfile, 'namespace Myriad {'
            print >> wfile, ''
            print >> wfile, '}  // namespace Myriad'
    
            wfile.close()


class RecordTypeCompiler(SourceCompiler):
    '''
    classdocs
    '''
    
    def __init__(self, *args, **kwargs):
        '''
        Constructor
        '''
        super(RecordTypeCompiler, self).__init__(*args, **kwargs)
        
    def compile(self, recordSequences):
        for recordSequence in recordSequences.getRecordSequences():
            self._log.warning("compiling record C++ sources for `%s`" % (recordSequence.getAttribute("key")))
            self.compileBaseRecordMeta(recordSequence.getRecordType())
            self.compileBaseRecordType(recordSequence.getRecordType())
            self.compileBaseRecordUtil(recordSequence.getRecordType())
            self.compileRecordMeta(recordSequence.getRecordType())
            self.compileRecordType(recordSequence.getRecordType())
            self.compileRecordUtil(recordSequence.getRecordType())
            
    def compileBaseRecordMeta(self, recordType):
        try:
            os.makedirs("%s/cpp/record/base" % (self._srcPath))
        except OSError:
            pass
        
        typeNameUS = recordType.getAttribute("key")
        typeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(typeNameUS))
        typeNameUC = StringTransformer.uc(typeNameCC)
        
        wfile = open("%s/cpp/record/base/Base%sMeta.h" % (self._srcPath, typeNameCC), "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '// auto-generatad C++ file for `%s`' % (recordType.getAttribute("key"))
        print >> wfile, ''
        print >> wfile, '#ifndef BASE%sMETA_H_' % (typeNameUC)
        print >> wfile, '#define BASE%sMETA_H_' % (typeNameUC)
        print >> wfile, ''
        print >> wfile, '#include "record/Record.h"'
        print >> wfile, ''
        print >> wfile, 'using namespace Myriad;'
        print >> wfile, ''
        print >> wfile, 'namespace %s {' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, '// forward declarations'
        print >> wfile, 'class %s;' % (typeNameCC)
        print >> wfile, ''
        print >> wfile, 'class Base%(t)sMeta : public RecordMeta<%(t)s>' % { 't': typeNameCC }
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        
        if recordType.hasEnumFields():
            print >> wfile, '    Base%(t)sMeta(const map<string, vector<string> >& enumSets) : ' % {'t': typeNameCC}
            print >> wfile, '        %s' % ', '.join([ '%(n)s(enumSets.find("%(r)s")->second)' % {'n': field.getAttribute("name"), 'r': field.getAttribute("enumref")} for field in recordType.getEnumFields() ])
            print >> wfile, '    {'
            print >> wfile, '    }'
        else:
            print >> wfile, '    Base%(t)sMeta(const map<string, vector<string> >& enumSets)' % {'t': typeNameCC}
            print >> wfile, '    {'
            print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    // enum set refecences'
        for field in recordType.getEnumFields():
            print >> wfile, '    const vector<String>& %s;' % field.getAttribute("name")
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '} // namespace %s' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, '#endif /* BASE%sMETA_H_ */' % (typeNameUC)

        wfile.close()
            
    def compileRecordMeta(self, recordType):
        try:
            os.makedirs("%s/cpp/record" % (self._srcPath))
        except OSError:
            pass
        
        typeNameUS = recordType.getAttribute("key")
        typeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(typeNameUS))
        typeNameUC = StringTransformer.uc(typeNameCC)
        
        sourcePath = "%s/cpp/record/%sMeta.h" % (self._srcPath, typeNameCC)
        
        if (os.path.isfile(sourcePath)):
            return
        
        wfile = open(sourcePath, "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '// auto-generatad C++ file for `%s`' % (recordType.getAttribute("key"))
        print >> wfile, ''
        print >> wfile, '#ifndef %sMETA_H_' % (typeNameUC)
        print >> wfile, '#define %sMETA_H_' % (typeNameUC)
        print >> wfile, ''
        print >> wfile, '#include "record/base/Base%sMeta.h"' % (typeNameCC)
        print >> wfile, ''
        print >> wfile, 'using namespace Myriad;'
        print >> wfile, ''
        print >> wfile, 'namespace %s {' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, 'class %(t)sMeta : public Base%(t)sMeta' % {'t': typeNameCC}
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    %(t)sMeta(const map<string, vector<string> >& enumSets) :' % {'t': typeNameCC}
        print >> wfile, '        Base%(t)sMeta(enumSets)' % {'t': typeNameCC}
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '} // namespace %s' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, '#endif /* %sMETA_H_ */' % (typeNameUC)

        wfile.close()
            
    def compileBaseRecordType(self, recordType):
        try:
            os.makedirs("%s/cpp/record/base" % (self._srcPath))
        except OSError:
            pass
        
        typeNameUS = recordType.getAttribute("key")
        typeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(typeNameUS))
        typeNameUC = StringTransformer.uc(typeNameCC)
        
        wfile = open("%s/cpp/record/base/Base%s.h" % (self._srcPath, typeNameCC), "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '// auto-generatad C++ file for `%s`' % (recordType.getAttribute("key"))
        print >> wfile, ''
        print >> wfile, '#ifndef BASE%s_H_' % (typeNameUC)
        print >> wfile, '#define BASE%s_H_' % (typeNameUC)
        print >> wfile, ''
        print >> wfile, '#include "record/Record.h"'
        print >> wfile, '#include "record/%sMeta.h"' % (typeNameCC)
        
        for referenceType in sorted(recordType.getReferenceTypes()):
            print >> wfile, '#include "record/%s.h"' % (StringTransformer.sourceType(referenceType))
        
        print >> wfile, ''
        print >> wfile, 'using namespace Myriad;'
        print >> wfile, ''
        print >> wfile, 'namespace %s {' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// forward declarations'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'class %s;' % (typeNameCC)
        print >> wfile, 'class %sConfig;' % (typeNameCC)
        print >> wfile, 'class %sGenerator;' % (typeNameCC)
        print >> wfile, 'class %sHydratorChain;' % (typeNameCC)
        print >> wfile, 'class %sRangePredicate;' % (typeNameCC)
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// base record type'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'class Base%s: public Record' % (typeNameCC)
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    Base%(t)s(const %(t)sMeta& meta) : ' % { 't': typeNameCC }
        print >> wfile, '        _meta(meta)'
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        
        for field in recordType.getFields():
            fieldType = field.getAttribute("type")
            fieldName = field.getAttribute("name")
            
                
            print >> wfile, '    void %s(const %s& v);' % (StringTransformer.us2cc(fieldName), StringTransformer.sourceType(fieldType))
            print >> wfile, '    const %s& %s() const;' % (StringTransformer.sourceType(fieldType), StringTransformer.us2cc(fieldName))
            
            if isinstance(field, RecordEnumFieldNode):
                print >> wfile, '    const String& %sEnumValue() const;' % (StringTransformer.us2cc(fieldName))

            print >> wfile, ''
            
            if StringTransformer.isVectorType(fieldType):
                print >> wfile, '    void %sSetOne(const %s& v, const size_t i = numeric_limits<size_t>::max());' % (StringTransformer.us2cc(fieldName), StringTransformer.coreType(fieldType))
                print >> wfile, '    const %s& %sGetOne(const size_t i) const;' % (StringTransformer.coreType(fieldType), StringTransformer.us2cc(fieldName))
                print >> wfile, ''
        
        for reference in recordType.getReferences():
            referenceType = reference.getAttribute("type")
            referenceName = reference.getAttribute("name")
            
            print >> wfile, '    void %s(const AutoPtr<%s>& v);' % (StringTransformer.us2cc(referenceName), StringTransformer.sourceType(referenceType))
            print >> wfile, '    const AutoPtr<%s>& %s() const;' % (StringTransformer.sourceType(referenceType), StringTransformer.us2cc(referenceName))
            print >> wfile, ''
        
        print >> wfile, 'protected:'
        print >> wfile, ''
        print >> wfile, '    // meta'
        print >> wfile, '    const %sMeta& _meta;' % (typeNameCC)

        if recordType.hasFields():
            print >> wfile, ''
            print >> wfile, '    // fields'
        for field in recordType.getFields():
            print >> wfile, '    %s _%s;' % (StringTransformer.sourceType(field.getAttribute("type")), field.getAttribute("name")) 
        
        if recordType.hasReferences():
            print >> wfile, ''
            print >> wfile, '    // references'
        for field in recordType.getReferences():
            print >> wfile, '    AutoPtr<%s> _%s;' % (StringTransformer.sourceType(field.getAttribute("type")), field.getAttribute("name")) 

        print >> wfile, '};'
        print >> wfile, ''
        
        for field in recordType.getFields():
            fieldType = field.getAttribute("type")
            fieldName = field.getAttribute("name")
            
            print >> wfile, 'inline void Base%s::%s(const %s& v)' % (typeNameCC, StringTransformer.us2cc(fieldName), StringTransformer.sourceType(fieldType))
            print >> wfile, '{'
            print >> wfile, '    _%s = v;' % (fieldName)
            print >> wfile, '}'
            print >> wfile, ''
            print >> wfile, 'inline const %s& Base%s::%s() const' % (StringTransformer.sourceType(fieldType), typeNameCC, StringTransformer.us2cc(fieldName))
            print >> wfile, '{'
            print >> wfile, '    return _%s;' % (fieldName)
            print >> wfile, '}'
            print >> wfile, ''
            
            if isinstance(field, RecordEnumFieldNode):
                print >> wfile, 'inline const String& Base%s::%sEnumValue() const' % (typeNameCC, StringTransformer.us2cc(fieldName))
                print >> wfile, '{'
                print >> wfile, '    return _meta.%(n)s[_%(n)s];' % {'n': fieldName}
                print >> wfile, '}'
                print >> wfile, ''

            if StringTransformer.isVectorType(fieldType):
                print >> wfile, 'inline void Base%s::%sSetOne(const %s& v, const size_t i)' % (typeNameCC, StringTransformer.us2cc(fieldName), StringTransformer.coreType(fieldType))
                print >> wfile, '{'
                print >> wfile, '    if (i == numeric_limits<size_t>::max())'
                print >> wfile, '    {'
                print >> wfile, '        _%s.push_back(v);' % (fieldName)
                print >> wfile, '    }'
                print >> wfile, '    else'
                print >> wfile, '    {'
                print >> wfile, '        _%s[i] = v;' % (fieldName)
                print >> wfile, '    }'
                print >> wfile, '}'
                print >> wfile, ''
                print >> wfile, 'inline const %s& Base%s::%sGetOne(const size_t i) const' % (StringTransformer.coreType(fieldType), typeNameCC, StringTransformer.us2cc(fieldName))
                print >> wfile, '{'
                print >> wfile, '    return _%s[i];' % (fieldName)
                print >> wfile, '}'
                print >> wfile, ''
        
        for reference in recordType.getReferences():
            referenceType = reference.getAttribute("type")
            referenceName = reference.getAttribute("name")
            
            print >> wfile, 'inline void Base%s::%s(const AutoPtr<%s>& v)' % (typeNameCC, StringTransformer.us2cc(referenceName), StringTransformer.sourceType(referenceType))
            print >> wfile, '{'
            print >> wfile, '    _%s = v;' % (referenceName)
            print >> wfile, '}'
            print >> wfile, ''
            print >> wfile, 'inline const AutoPtr<%s>& Base%s::%s() const' % (StringTransformer.sourceType(referenceType), typeNameCC, StringTransformer.us2cc(referenceName))
            print >> wfile, '{'
            print >> wfile, '    return _%s;' % (referenceName)
            print >> wfile, '}'
            print >> wfile, ''
        
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// base range predicate type'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'class Base%(t)sRangePredicate: public RecordRangePredicate<%(t)s>' % { 't': typeNameCC }
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    Base%(t)sRangePredicate()' % { 't': typeNameCC }
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        
        for field in recordType.getFields():
            fieldType = field.getAttribute("type")
            fieldName = field.getAttribute("name")
                
            if StringTransformer.isNumericType(fieldType):
                parameters = {'n' : StringTransformer.us2cc(fieldName), 't': StringTransformer.sourceType(fieldType)}
                print >> wfile, '    void %(n)s(%(t)s min, %(t)s max);' % parameters
                print >> wfile, '    void %(n)s(%(t)s v);' % parameters
                print >> wfile, '    const Interval<%(t)s>& %(n)s() const;' % parameters
                print >> wfile, ''
        
        print >> wfile, 'protected:'
        print >> wfile, ''
        print >> wfile, '    // fields'

        for field in recordType.getFields():
            fieldType = field.getAttribute("type")
            fieldName = field.getAttribute("name")
                
            if StringTransformer.isNumericType(fieldType):
                print >> wfile, '    Interval<%s> _%s_range;' % (StringTransformer.sourceType(field.getAttribute("type")), field.getAttribute("name"))
            
        print >> wfile, '};'
        print >> wfile, ''

        for field in recordType.getFields():
            fieldType = field.getAttribute("type")
            fieldName = field.getAttribute("name")

            if StringTransformer.isNumericType(fieldType):
                parameters = {'T': typeNameCC, 'n' : StringTransformer.us2cc(fieldName), 't': StringTransformer.sourceType(fieldType)}
                print >> wfile, 'inline void Base%(T)sRangePredicate::%(n)s(%(t)s min, %(t)s max)' % parameters
                print >> wfile, '{'
                print >> wfile, '    _%s_range.set(min, max);' % (fieldName)
                print >> wfile, '}'
                print >> wfile, ''
                print >> wfile, 'inline void Base%(T)sRangePredicate::%(n)s(%(t)s v)' % parameters
                print >> wfile, '{'
                print >> wfile, '    _%s_range.set(v++, v);' % (fieldName)
                print >> wfile, '}'
                print >> wfile, ''
                print >> wfile, 'inline const Interval<%(t)s>& Base%(T)sRangePredicate::%(n)s() const' % parameters
                print >> wfile, '{'
                print >> wfile, '    return _%s_range;' % (fieldName)
                print >> wfile, '}'
                print >> wfile, '' 
        
        print >> wfile, '} // namespace %s' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, 'namespace Myriad {'
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// record traits specialization'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        
        fieldConstants = []
        fieldConstants.extend([StringTransformer.uc(field.getAttribute("name")) for field in sorted(recordType.getFields(), key=lambda f: f.orderkey)])
        fieldConstants.extend([StringTransformer.uc(field.getAttribute("name")) for field in sorted(recordType.getReferences(), key=lambda f: f.orderkey)])

        print >> wfile, 'template<>'
        print >> wfile, 'struct RecordTraits<%s::%s>' % (self._args.dgen_ns, typeNameCC)
        print >> wfile, '{'
        print >> wfile, '    typedef %s::%sMeta MetaType;' % (self._args.dgen_ns, typeNameCC)
        print >> wfile, '    typedef %s::%sGenerator GeneratorType;' % (self._args.dgen_ns, typeNameCC)
        print >> wfile, '    typedef %s::%sHydratorChain HydratorChainType;' % (self._args.dgen_ns, typeNameCC)
        print >> wfile, '    typedef RecordFactory<%s::%s> FactoryType;' % (self._args.dgen_ns, typeNameCC)
        print >> wfile, '    typedef %s::%sRangePredicate RangePredicateType;' % (self._args.dgen_ns, typeNameCC)
        print >> wfile, ''
        print >> wfile, '    enum Field { UNKNOWN, GEN_ID, %s };' % ', '.join(fieldConstants)
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// serialize method specialization'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'template<>' 
        print >> wfile, 'inline void OutputCollector<%(ns)s::Base%(t)s>::CollectorType::serialize(OutputCollector<%(ns)s::%(t)s>::CollectorType::StreamType& out, const %(ns)s::Base%(t)s& record)' % {'ns': self._args.dgen_ns, 't': typeNameCC}
        print >> wfile, '{'
        
        for field in sorted(recordType.getFields(), key=lambda f: f.orderkey):
            fieldType = field.getAttribute("type")
            fieldName = field.getAttribute("name")
            
            if StringTransformer.isVectorType(fieldType):
                raise RuntimeError("Unsupported vector type field '%s'" % fieldType)
            elif fieldType == "Enum":
                print >> wfile, '    write(out, %s, false);' % ("record." + StringTransformer.us2cc(fieldName) + "EnumValue()")
                print >> wfile, '    out << \'|\';'
            else:
                print >> wfile, '    write(out, %s, false);' % ("record." + StringTransformer.us2cc(fieldName) + "()")
                print >> wfile, '    out << \'|\';'

        print >> wfile, '    out << \'\\n\';'
        print >> wfile, '}'
        print >> wfile, ''
        print >> wfile, '} // namespace Myriad'
        print >> wfile, ''
        print >> wfile, '#endif /* BASE%s_H_ */' % (typeNameUC)

        wfile.close()
    
    def compileRecordType(self, recordType):
        try:
            os.makedirs("%s/cpp/record" % (self._srcPath))
        except OSError:
            pass
        
        typeNameUS = recordType.getAttribute("key")
        typeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(typeNameUS))
        typeNameUC = StringTransformer.uc(typeNameCC)
        
        sourcePath = "%s/cpp/record/%s.h" % (self._srcPath, typeNameCC)
        
        if (os.path.isfile(sourcePath)):
            return
        
        wfile = open(sourcePath, "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '#ifndef %s_H_' % (typeNameUC)
        print >> wfile, '#define %s_H_' % (typeNameUC)
        print >> wfile, ''
        print >> wfile, '#include "record/base/Base%s.h"' % (typeNameCC)
        print >> wfile, ''
        print >> wfile, 'using namespace Myriad;'
        print >> wfile, ''
        print >> wfile, 'namespace %s {' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// record type'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'class %(t)s: public Base%(t)s' % {'t': typeNameCC}
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    %(t)s(const %(t)sMeta& meta)' % {'t': typeNameCC}
        print >> wfile, '        : Base%s(meta)' % (typeNameCC)
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// range predicate type'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'class %(t)sRangePredicate: public Base%(t)sRangePredicate' % { 't': typeNameCC }
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    %(t)sRangePredicate()' % { 't': typeNameCC }
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '} // namespace %s' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, 'namespace Myriad {'
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// record serialize method specialization'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'template<>'
        print >> wfile, 'inline void OutputCollector<%(ns)s::%(t)s>::CollectorType::serialize(OutputCollector<%(ns)s::%(t)s>::CollectorType::StreamType& out, const %(ns)s::%(t)s& record)' % {'ns': self._args.dgen_ns, 't': typeNameCC}
        print >> wfile, '{'
        print >> wfile, '    OutputCollector<%(ns)s::Base%(t)s>::CollectorType::serialize(out, record);' % {'ns': self._args.dgen_ns, 't': typeNameCC}
        print >> wfile, '}'
        print >> wfile, ''
        print >> wfile, '} // namespace Myriad'
        print >> wfile, ''
        print >> wfile, '#endif /* %s_H_ */' % (typeNameUC)

        wfile.close()
            
    def compileBaseRecordUtil(self, recordType):
        try:
            os.makedirs("%s/cpp/record/base" % (self._srcPath))
        except OSError:
            pass
        
        typeNameUS = recordType.getAttribute("key")
        typeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(typeNameUS))
        typeNameUC = StringTransformer.uc(typeNameCC)
        
        wfile = open("%s/cpp/record/base/Base%sUtil.h" % (self._srcPath, typeNameCC), "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '// auto-generatad C++ file for `%s`' % (recordType.getAttribute("key"))
        print >> wfile, ''
        print >> wfile, '#ifndef BASE%sUTIL_H_' % (typeNameUC)
        print >> wfile, '#define BASE%sUTIL_H_' % (typeNameUC)
        print >> wfile, ''
        print >> wfile, '#include "record/%s.h"' % (typeNameCC)
        print >> wfile, ''
        print >> wfile, 'namespace Myriad {'
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// record field inspection structures'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        
        for field in sorted(recordType.getFields(), key=lambda f: f.orderkey):
            fieldType = field.getAttribute("type")
            fieldName = field.getAttribute("name")
            
            parameters = {'ns': self._args.dgen_ns, 't': typeNameCC, 'k': StringTransformer.uc(fieldName), 'f': StringTransformer.us2cc(fieldName)}
            print >> wfile, ''
            print >> wfile, '// %s' % (fieldName)
            print >> wfile, 'template<>'
            print >> wfile, 'struct RecordFieldTraits<RecordTraits<%(ns)s::%(t)s>::%(k)s, %(ns)s::%(t)s>' % parameters
            print >> wfile, '{'
            print >> wfile, '    typedef %s FieldType;' % (fieldType)
            print >> wfile, '    // record field getter / setter types'
            print >> wfile, '    typedef typename MethodTraits<%(ns)s::%(t)s, FieldType>::Setter FieldSetterType;' % parameters
            print >> wfile, '    typedef typename MethodTraits<%(ns)s::%(t)s, FieldType>::Getter FieldGetterType;' % parameters
            print >> wfile, '    // range predicate getter / setter types'
            print >> wfile, '    typedef typename RecordTraits<%(ns)s::%(t)s>::RangePredicateType RecordRangePredicateType;' % parameters
            print >> wfile, '    typedef typename MethodTraits<RecordRangePredicateType, FieldType>::RangeSetterShort RangeSetterShortType;'
            print >> wfile, '    typedef typename MethodTraits<RecordRangePredicateType, FieldType>::RangeSetterLong RangeSetterLongType;'
            print >> wfile, '    typedef typename MethodTraits<RecordRangePredicateType, FieldType>::RangeGetter RangeGetterType;'
            print >> wfile, ''
            print >> wfile, '    static inline FieldSetterType setter()'
            print >> wfile, '    {'
            print >> wfile, '        return static_cast<FieldSetterType>(&%(ns)s::%(t)s::%(f)s);' % parameters
            print >> wfile, '    }'
            print >> wfile, ''
            print >> wfile, '    static inline FieldGetterType getter()'
            print >> wfile, '    {'
            print >> wfile, '        return static_cast<FieldGetterType>(&%(ns)s::%(t)s::%(f)s);' % parameters
            print >> wfile, '    }'
            
            if StringTransformer.isNumericType(fieldType):
                print >> wfile, ''
                print >> wfile, '    static inline RangeSetterShortType rangeSetterShort()'
                print >> wfile, '    {'
                print >> wfile, '        return static_cast<RangeSetterShortType>(&RecordRangePredicateType::%(f)s);' % parameters
                print >> wfile, '    }'
                print >> wfile, ''
                print >> wfile, '    static inline RangeSetterLongType rangeSetterLong()'
                print >> wfile, '    {'
                print >> wfile, '        return static_cast<RangeSetterLongType>(&RecordRangePredicateType::%(f)s);' % parameters
                print >> wfile, '    }'
                print >> wfile, ''
                print >> wfile, '    static inline RangeGetterType rangeGetter()'
                print >> wfile, '    {'
                print >> wfile, '        return static_cast<RangeGetterType>(&RecordRangePredicateType::%(f)s);' % parameters
                print >> wfile, '    }'
            else:
                print >> wfile, ''
                print >> wfile, '    static inline RangeSetterShortType rangeSetterShort()'
                print >> wfile, '    {'
                print >> wfile, '        throw RuntimeException("Trying to access record range predicate setter for non-numeric field `%s`");' % fieldName      
                print >> wfile, '    }'
                print >> wfile, ''
                print >> wfile, '    static inline RangeSetterLongType rangeSetterLong()'
                print >> wfile, '    {'
                print >> wfile, '        throw RuntimeException("Trying to access record range predicate setter for non-numeric field `%s`");' % fieldName
                print >> wfile, '    }'
                print >> wfile, ''
                print >> wfile, '    static inline RangeGetterType rangeGetter()'
                print >> wfile, '    {'
                print >> wfile, '        throw RuntimeException("Trying to access record range predicate getter for non-numeric field `%s`");' % fieldName
                print >> wfile, '    }'
            print >> wfile, '};'
        
        for field in sorted(recordType.getReferences(), key=lambda f: f.orderkey):
            fieldType = field.getAttribute("type")
            fieldName = field.getAttribute("name")
            
            parameters = {'ns': self._args.dgen_ns, 't': typeNameCC, 'k': StringTransformer.uc(fieldName), 'f': StringTransformer.us2cc(fieldName)}
            print >> wfile, ''
            print >> wfile, '// %s' % (fieldName)
            print >> wfile, 'template<>'
            print >> wfile, 'struct RecordFieldTraits<RecordTraits<%(ns)s::%(t)s>::%(k)s, %(ns)s::%(t)s>' % parameters
            print >> wfile, '{'
            print >> wfile, '    typedef %s::%s FieldType;' % (self._args.dgen_ns, fieldType)
            print >> wfile, '    // record field getter / setter types'
            print >> wfile, '    typedef typename MethodTraits<%(ns)s::%(t)s, AutoPtr<FieldType> >::Setter FieldSetterType;' % parameters
            print >> wfile, '    typedef typename MethodTraits<%(ns)s::%(t)s, AutoPtr<FieldType> >::Getter FieldGetterType;' % parameters
            print >> wfile, '    // range predicate getter / setter types'
            print >> wfile, '    typedef typename RecordTraits<%(ns)s::%(t)s>::RangePredicateType RecordRangePredicateType;' % parameters
            print >> wfile, '    typedef typename MethodTraits<RecordRangePredicateType, AutoPtr<FieldType> >::RangeSetterShort RangeSetterShortType;'
            print >> wfile, '    typedef typename MethodTraits<RecordRangePredicateType, AutoPtr<FieldType> >::RangeSetterLong RangeSetterLongType;'
            print >> wfile, '    typedef typename MethodTraits<RecordRangePredicateType, AutoPtr<FieldType> >::RangeGetter RangeGetterType;'
            print >> wfile, ''
            print >> wfile, '    static inline FieldSetterType setter()'
            print >> wfile, '    {'
            print >> wfile, '        return static_cast<FieldSetterType>(&%(ns)s::%(t)s::%(f)s);' % parameters
            print >> wfile, '    }'
            print >> wfile, ''
            print >> wfile, '    static inline FieldGetterType getter()'
            print >> wfile, '    {'
            print >> wfile, '        return static_cast<FieldGetterType>(&%(ns)s::%(t)s::%(f)s);' % parameters
            print >> wfile, '    }'
            print >> wfile, ''
            print >> wfile, '    static inline RangeSetterShortType rangeSetterShort()'
            print >> wfile, '    {'
            print >> wfile, '        throw RuntimeException("Trying to access record range predicate setter for non-numeric field `%s`");' % fieldName      
            print >> wfile, '    }'
            print >> wfile, ''
            print >> wfile, '    static inline RangeSetterLongType rangeSetterLong()'
            print >> wfile, '    {'
            print >> wfile, '        throw RuntimeException("Trying to access record range predicate setter for non-numeric field `%s`");' % fieldName
            print >> wfile, '    }'
            print >> wfile, ''
            print >> wfile, '    static inline RangeGetterType rangeGetter()'
            print >> wfile, '    {'
            print >> wfile, '        throw RuntimeException("Trying to access record range predicate getter for non-numeric field `%s`");' % fieldName
            print >> wfile, '    }'
            print >> wfile, '};'
        
        print >> wfile, ''
        print >> wfile, '} // namespace Myriad'
        print >> wfile, ''
        print >> wfile, '#endif /* BASE%sUTIL_H_ */' % (typeNameUC)

        wfile.close()
    
    def compileRecordUtil(self, recordType):
        try:
            os.makedirs("%s/cpp/record" % (self._srcPath))
        except OSError:
            pass
        
        typeNameUS = recordType.getAttribute("key")
        typeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(typeNameUS))
        typeNameUC = StringTransformer.uc(typeNameCC)
        
        sourcePath = "%s/cpp/record/%sUtil.h" % (self._srcPath, typeNameCC)
        
        if (os.path.isfile(sourcePath)):
            return
        
        wfile = open(sourcePath, "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '#ifndef %sUTIL_H_' % (typeNameUC)
        print >> wfile, '#define %sUTIL_H_' % (typeNameUC)
        print >> wfile, ''
        print >> wfile, '#include "record/base/Base%sUtil.h"' % (typeNameCC)
        print >> wfile, ''
        print >> wfile, 'namespace Myriad {'
        print >> wfile, ''
        print >> wfile, '// put your extra RecordFieldTraits specializations here'
        print >> wfile, ''
        print >> wfile, '} // namespace Myriad'
        print >> wfile, ''
        print >> wfile, '#endif /* %sUTIL_H_ */' % (typeNameUC)


class RecordGeneratorCompiler(SourceCompiler):
    '''
    classdocs
    '''
    
    _getter_pattern = re.compile('getter\(([a-zA-Z_]+)\)')
    
    def __init__(self, *args, **kwargs):
        '''
        Constructor
        '''
        super(RecordGeneratorCompiler, self).__init__(*args, **kwargs)
        
    def compile(self, recordSequences):
        for recordSequence in recordSequences.getRecordSequences():
            self._log.warning("compiling generator C++ sources for `%s`" % (recordSequence.getAttribute("key")))
            self.compileBaseGenerator(recordSequence)
            self.compileGenerator(recordSequence)
            
    def compileBaseGenerator(self, recordSequence):
        try:
            os.makedirs("%s/cpp/generator/base" % (self._srcPath))
        except OSError:
            pass
        
        if isinstance(recordSequence, RandomSequenceNode):
            self.__compileBaseRandomGenerator(recordSequence)
        else:
            self._log.warning("unsupported generator type for sequence `%s`" % (recordSequence.getAttribute("key")))

    def __compileBaseRandomGenerator(self, recordSequence):
        typeNameUS = recordSequence.getAttribute("key")
        typeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(typeNameUS))
        typeNameUC = StringTransformer.uc(typeNameCC)
        
        sourcePath = "%s/cpp/generator/base/Base%sGenerator.h" % (self._srcPath, typeNameCC)
        
        wfile = open(sourcePath, "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '// auto-generatad C++ generator for `%s`' % (typeNameUS)
        print >> wfile, ''
        print >> wfile, '#ifndef BASE%sGENERATOR_H_' % (typeNameUC)
        print >> wfile, '#define BASE%sGENERATOR_H_' % (typeNameUC)
        print >> wfile, ''
        print >> wfile, '#include "generator/RandomSetGenerator.h"'
        
        for referenceType in sorted(recordSequence.getRecordType().getReferenceTypes()):
            print >> wfile, '#include "generator/%sGenerator.h"' % (StringTransformer.sourceType(referenceType))
            
        print >> wfile, '#include "record/%s.h"' % (typeNameCC)
        print >> wfile, '#include "record/%sUtil.h"' % (typeNameCC)
        
        for hydrator in sorted(recordSequence.getHydrators().getAll(), key=lambda h: h.orderkey):
            print >> wfile, '#include "hydrator/%s.h"' % (hydrator.getAttribute("template_type"))
        
        print >> wfile, ''
        print >> wfile, 'using namespace Myriad;'
        print >> wfile, ''
        print >> wfile, 'namespace %s {' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// RecordGenerator specialization (base class)'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'class Base%(t)sGenerator: public RandomSetGenerator<%(t)s>' % {'t': typeNameCC}
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    Base%sGenerator(const string& name, GeneratorConfig& config, NotificationCenter& notificationCenter) :' % (typeNameCC)
        print >> wfile, '        RandomSetGenerator<%s>(name, config, notificationCenter)' % (typeNameCC)
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    void prepare(Stage stage, const GeneratorPool& pool)'
        print >> wfile, '    {'
        print >> wfile, '        // call generator implementation'
        print >> wfile, '        RandomSetGenerator<%s>::prepare(stage, pool);' % (typeNameCC)
        
        if recordSequence.hasSequenceIterator():
            sequenceIterator = recordSequence.getSequenceIterator()
            sequenceIteratorArgsCode = ArgumentTransformer.compileConstructorArguments(self, sequenceIterator, {'config': '_config'})
            
            print >> wfile, ''
            print >> wfile, '        if (stage.name() == name())'
            print >> wfile, '        {'
            print >> wfile, '            registerTask(new %s (%s));' % (sequenceIterator.getConcreteType(), ', '.join(sequenceIteratorArgsCode))
            print >> wfile, '        }'
            
        print >> wfile, '    }'
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// HydratorChain specialization (base class)'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, '/**'
        print >> wfile, ' * Hydrator specialization for User.'
        print >> wfile, ' */'
        print >> wfile, 'class Base%(t)sHydratorChain : public HydratorChain<%(t)s>' % {'t': typeNameCC}
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        
        print >> wfile, '    // hydrator typedefs'
        for hydrator in sorted(recordSequence.getHydrators().getAll(), key=lambda h: h.orderkey):
            print >> wfile, '    typedef %s %s;' % (hydrator.getConcreteType(), hydrator.getAttribute("type_alias"))
            
        print >> wfile, ''
        print >> wfile, '    Base%sHydratorChain(OperationMode& opMode, RandomStream& random, GeneratorConfig& config) :' % (typeNameCC)
        print >> wfile, '        HydratorChain<%s>(opMode, random),' % (typeNameCC)
        
        for hydrator in sorted(recordSequence.getHydrators().getAll(), key=lambda h: h.orderkey):
            argsCode = ArgumentTransformer.compileConstructorArguments(self, hydrator, {'config': 'config'})
            print >> wfile, '        _%s(%s),' % (StringTransformer.us2cc(hydrator.getAttribute("key")), ', '.join(argsCode))
        
        print >> wfile, '        _logger(Logger::get("%s.hydrator"))' % (typeNameUS)
            
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    virtual ~Base%sHydratorChain()' % (typeNameCC)
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    /**'
        print >> wfile, '     * Object hydrating function.'
        print >> wfile, '     */'
        print >> wfile, '    void operator()(AutoPtr<%s> recordPtr) const' % (typeNameCC)
        print >> wfile, '    {'
        print >> wfile, '        ensurePosition(recordPtr->genID());'
        print >> wfile, ''
        
        for hydrator in recordSequence.getHydrationPlan().getAll():
            print >> wfile, '        apply(_%s, recordPtr);' % (StringTransformer.us2cc(hydrator.getAttribute("key")))
        
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    /**'
        print >> wfile, '     * Invertible hydrator getter.'
        print >> wfile, '     */'
        print >> wfile, '    template<typename T>' 
        print >> wfile, '    const InvertibleHydrator<%(t)s, T>& invertableHydrator(typename MethodTraits<%(t)s, T>::Setter setter)' % {'t': typeNameCC}
        print >> wfile, '    {'
        print >> wfile, '        return HydratorChain<%s>::invertableHydrator<T>(setter);' % (typeNameCC)
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, 'protected:'
        print >> wfile, ''
        
        print >> wfile, '    // hydrator members'
        for hydrator in sorted(recordSequence.getHydrators().getAll(), key=lambda h: h.orderkey):
            print >> wfile, '    %s _%s;' % (hydrator.getAttribute("type_alias"), StringTransformer.us2cc(hydrator.getAttribute("key")))
        
        print >> wfile, ''
        print >> wfile, '    /**'
        print >> wfile, '     * Logger instance.'
        print >> wfile, '     */'
        print >> wfile, '    Logger& _logger;'
        print >> wfile, '};'
        print >> wfile, ''
        
        invertibleHydrators = {}
        for hydrator in sorted(recordSequence.getHydrators().getAll(), key=lambda h: h.orderkey):
            if hydrator.isInvertible():
                fieldType = hydrator.getArgument("field").getFieldRef().getAttribute("type")
                # treat Enum types as I64u / I32u depending on the C++ architecture
                if fieldType == 'Enum':
                    if self._args.is_arch64:
                        fieldType = 'I64u'
                    else:
                        fieldType = 'I32u'
                # lazy initialize container array for this fieldType
                if not invertibleHydrators.has_key(fieldType):
                    invertibleHydrators[fieldType] = []
                # append hydrator to the container array
                invertibleHydrators[fieldType].append(hydrator)
        
        for fieldType in sorted(invertibleHydrators.keys()):
            print >> wfile, '/**'
            print >> wfile, ' * Invertible hydrator getter (%s specialization).' % (fieldType)
            print >> wfile, ' */'
            print >> wfile, 'template<>' 
            print >> wfile, 'const InvertibleHydrator<%(rt)s, %(ft)s>& Base%(rt)sHydratorChain::invertableHydrator<%(ft)s>(MethodTraits<%(rt)s, %(ft)s>::Setter setter)' % { 'rt': typeNameCC, 'ft': fieldType}
            print >> wfile, '{'
            
            fieldSetterTransformer = FieldSetterTransfomer()
            for hydrator in invertibleHydrators[fieldType]:
                print >> wfile, '    if (setter == static_cast<MethodTraits<%(rt)s, %(ft)s>::Setter>(%(fs)s))' % { 'rt': typeNameCC, 'ft': fieldType, 'fs': fieldSetterTransformer.transform(hydrator.getArgument("field"))}
                print >> wfile, '    {'
                print >> wfile, '        return _%s;' % (StringTransformer.us2cc(hydrator.getAttribute("key")))
                print >> wfile, '    }'
            print >> wfile, ''
            print >> wfile, '    return HydratorChain<%(rt)s>::invertableHydrator<%(ft)s>(setter);' % { 'rt': typeNameCC, 'ft': fieldType}
            print >> wfile, '}'
        
        print >> wfile, ''
        print >> wfile, '} // namespace %s' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, '#endif /* BASE%sGENERATOR_H_ */' % (typeNameUC)

        wfile.close()
            
    def compileGenerator(self, recordSequence):
        try:
            os.makedirs("%s/cpp/generator" % (self._srcPath))
        except OSError:
            pass
        
        if isinstance(recordSequence, RandomSequenceNode):
            self.__compileRandomGenerator(recordSequence)
        else:
            self._log.warning("unsupported generator type for sequence `%s`" % (recordSequence.getAttribute("key")))

    def __compileRandomGenerator(self, recordSequence):
        typeNameUS = recordSequence.getAttribute("key")
        typeNameCC = StringTransformer.ucFirst(StringTransformer.us2cc(typeNameUS))
        typeNameUC = StringTransformer.uc(typeNameCC)
        
        sourcePath = "%s/cpp/generator/%sGenerator.h" % (self._srcPath, typeNameCC)
        
        if (os.path.isfile(sourcePath)):
            return
        
        wfile = open(sourcePath, "w", SourceCompiler.BUFFER_SIZE)
        
        print >> wfile, '#ifndef %sGENERATOR_H_' % (typeNameUC)
        print >> wfile, '#define %sGENERATOR_H_' % (typeNameUC)
        print >> wfile, ''
        print >> wfile, '#include "generator/base/Base%sGenerator.h"' % (typeNameCC)
        print >> wfile, ''
        print >> wfile, 'using namespace Myriad;'
        print >> wfile, ''
        print >> wfile, 'namespace %s {' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// RecordGenerator specialization'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'class %(t)sGenerator: public Base%(t)sGenerator' % {'t': typeNameCC}
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    typedef RecordTraits<%s>::HydratorChainType HydratorChainType;' % (typeNameCC)
        print >> wfile, ''
        print >> wfile, '    %sGenerator(const string& name, GeneratorConfig& config, NotificationCenter& notificationCenter) :' % (typeNameCC)
        print >> wfile, '        Base%sGenerator(name, config, notificationCenter)' % (typeNameCC)
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    HydratorChainType hydratorChain(BaseHydratorChain::OperationMode opMode, RandomStream& random);'
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// HydratorChain specialization'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'class %(t)sHydratorChain : public Base%(t)sHydratorChain' % {'t': typeNameCC}
        print >> wfile, '{'
        print >> wfile, 'public:'
        print >> wfile, ''
        print >> wfile, '    %sHydratorChain(OperationMode& opMode, RandomStream& random, GeneratorConfig& config) :' % (typeNameCC)
        print >> wfile, '        Base%sHydratorChain(opMode, random, config)' % (typeNameCC)
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, ''
        print >> wfile, '    virtual ~%sHydratorChain()' % (typeNameCC)
        print >> wfile, '    {'
        print >> wfile, '    }'
        print >> wfile, '};'
        print >> wfile, ''
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, '// base method definitions (don\'t modify)'
        print >> wfile, '// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~'
        print >> wfile, ''
        print >> wfile, 'inline %(t)sHydratorChain %(t)sGenerator::hydratorChain(BaseHydratorChain::OperationMode opMode, RandomStream& random)' % {'t': typeNameCC}
        print >> wfile, '{'
        print >> wfile, '    return %sHydratorChain(opMode, random, _config);' % (typeNameCC)
        print >> wfile, '}'
        print >> wfile, ''
        print >> wfile, '} // namespace %s' % (self._args.dgen_ns)
        print >> wfile, ''
        print >> wfile, '#endif /* BASE%sGENERATOR_H_ */' % (typeNameUC)

        wfile.close()