from .. import msg
from fortpy.testing.method import MethodWriter
from os import path, mkdir, remove
from datetime import datetime
from fortpy.interop.make import makefile

class ExecutableGenerator(object):
    """Generates a fortran executable to perform unit tests for a given
    subroutine or function.

    :arg parser: an instance of the code parser for inter-module access
    :arg folder: the folder in which to generate the code files and execs.
    :arg testgen: the TestGenerator instance that owns this executable generator.
    """
    def __init__(self, parser, folder, testgen):
        #We need the code parser because the pre-reqs specified may be in other
        #modules and may have pre-reqs of their own. This way, we can find
        #them all easily.
        self.parser = parser
        self.folder = folder
        self.testgen = testgen

        self._needs = None

    def needs(self):
        """Returns a list of all the modules that this executable needs to
        run correctly."""
        if self._needs is None:
            self._needs = self._calc_needs()
        return self._needs

    def _calc_needs(self):
        """Calculates a list of all the modules that this executable needs to
        run correctly."""
        result = []        
        for modk in self.writer.uses():
            if modk not in result:
                result.append(modk)

        #We also need to look up the dependencies of each of these modules
        recursed = list(result)
        for i in range(len(result)):
            module = result[i]
            self._process_module_needs(module, i, recursed)

        return recursed

    def _process_module_needs(self, module, i, result):
        """Adds the module and its dependencies to the result list."""
        #Some code might decide to use the fortpy module methods for general
        #development, ignore it since we know it will be present in the end.
        if module == "fortpy":
            return

        #See if the parser has alread loaded this module.
        if module not in self.parser.modules:
            self.parser.load_dependency(module, True, True, False)

        #It is possible that the parser couldn't find it, if so
        #we can't create the executable!
        if module in self.parser.modules:
            modneeds = self.parser.modules[module].needs
            for modn in modneeds:
                if modn not in result:
                    #Since this module depends on the other, insert the other
                    #above it in the list.
                    result.insert(i, modn)
                else:
                    x = result.index(modn)
                    if x > i:
                        #We need to move this module higher up in the food chain
                        #because it is needed sooner.
                        result.remove(modn)
                        result.insert(i, modn)

                newi = result.index(modn)
                self._process_module_needs(modn, newi, result)
        else:
            raise ValueError("unable to find module {}.".format(module))

    def reset(self, identifier, libraryroot, rerun=None):
        """Resets the writer to work with a new executable."""        
        #A method writer has all the guts needed to generate the executable
        #We are just wrapping it and making sure the variable values get
        #recorded to temporary files for comparison etc.
        self.identifier = identifier
        self.folder = path.expanduser(path.join(libraryroot, identifier))
        self._needs = None

        #Create the directory for the executable files to be copied and written to.
        if not path.exists(self.folder):
            msg.okay("EXEC DIR: create {}".format(self.folder))
            mkdir(self.folder)

        #If re-run is specified, delete the fortpy.f90 file to force
        #a quick re-compile and run of the tests.
        if rerun is not None and (rerun == "*" or rerun in identifier.lower()):
            fortpath = path.join(self.folder, "fortpy.f90")
            if path.exists(fortpath):
                remove(fortpath)
            
        self.writer = MethodWriter(identifier, self.parser, self.testgen)

    def write(self, testid):
        """Writes the fortran program file for the executable specified.

        :arg testid: the identifier of the test to construct the executable for.
        """
        lines = []
        identifier = self.writer.tests[testid].identifier

        #First off, we need to start the program and set the module dependencies.
        lines.append("!!<summary>Auto-generated unit test for {}\n".format(
            self.identifier))
        lines.append("!!using FORTPY. Generated on {}.\n".format(datetime.now()))
        lines.append("!!{}</summary>\n".format(self.writer.tests[testid].description))
        lines.append("PROGRAM UNITTEST_{}\n".format(self.writer.finders[testid].executable.name))
        lines.append(self._get_uses(testid))
        lines.append("  implicit none\n")

        #Next add the variable declarations and initializations and the calls
        #to execute the pre-req methods and the one we are trying to test.
        lines.append(self.writer.lines(testid))

        lines.append("\nEND PROGRAM UNITTEST_{}".format(self.writer.finders[testid].executable.name))

        with open(path.join(self.folder, "{}.f90".format(identifier)), 'w') as f:
            f.writelines(lines)
        
    def makefile(self, identifier):
        """Generates a makefile to create the unit testing executable
        for the specified test identifier.

        :arg identifier: the id of the test that this executable should be made for.
        """
        allneeds = self.needs()
        #We need to see whether to include the pre-compiler directive or not.
        precompile = False
        for needed in allneeds:
            if self.parser.modules[needed].precompile:
                precompile = True
                break

        lines = []
        makepath = path.join(self.folder, "Makefile.{}".format(identifier))
        makefile(identifier, allneeds, makepath, self.identifier, precompile, parser=self.parser)
        
    def _get_uses(self, testid):
        """Gets a list of use statements to add to the program code."""
        #The writer can extract a dictionary of module dependencies for us.
        alluses = self.writer.uses()
        #Now we just need to generate the code statements.
        uselist = []
        for module in alluses:
            if module == self.writer.finders[testid].module.name:
                uselist.append("use {}".format(module))
            else:
                uselist.append("use {}, only: {}".format(module, ", ".join(alluses[module])))

        #Last of all, we need to append the module that handles interaction with
        #the fortran results and the python testing framework.
        if "fortpy" not in alluses:
            uselist.append("use fortpy\n")

        return self._tabjoin(uselist)

    def _tabjoin(self, values):
        """Joins a list of values with \t\n."""
        return "  {}".format("\n  ".join(values))
