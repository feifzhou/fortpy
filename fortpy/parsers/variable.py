import re
from ..elements import ValueElement

class VariableParser(object):
    """Extracts members, locals and parameter definitions from fortran code."""
    def __init__(self):
        self.setup_regex()

    def setup_regex(self):
        "Sets up all the patterns and compiled regexes for extracting variables."""        
        #Regex for finding members of a type
        self._RX_MEMBERS = r"^\s*(?P<type>character|real|type|logical|integer|class)" + \
                           r"(?P<kind>\([A-Za-z0-9_=*]+\))?" + \
                           r",?(?P<modifiers>[ \w\t:,()]+)?::\s*(?P<names>[^\n!]+)" #Removed $ from end.
        self.RE_MEMBERS = re.compile(self._RX_MEMBERS, re.M | re.I)

        self._RX_MULTIDEF = r"(?P<name>[^(,=]+)(?P<dimension>\([^)]+\))?(\s?=?\s*(?P<default>.+))?"
        self.RE_MULTIDEF = re.compile(self._RX_MULTIDEF, re.I)

    def parse(self, string, parent):
        """Parses all the value code elements from the specified string."""
        result = {}
        for member in self.RE_MEMBERS.finditer(string):
            mems = self._process_member(member, parent)
            #The regex match could contain multiple members that were defined
            #on the same line in the code file.
            for onemem in mems:
                result[onemem.name.lower()] = onemem
                
        return result

    def _process_member(self, member, parent):
        """Extracts all the member info from the regex match; returns a ValueElements."""
        #The modifiers regex is very greedy so we have some cleaning up to do
        #to extract the mods.
        modifiers = member.group("modifiers")
        dimension = None
        
        if modifiers is not None:
            #Unfortunately, the dimension can also be specified as a modifier and
            #the dimensions can include variable names and functions. This introduces
            #the possibility of nested lists.
            if "dimension" in modifiers:
                start, end = self._get_dim_modifier(modifiers)
                dimension = modifiers[start+1:end]
                dimtext = modifiers[modifiers.index("dimension"):end+1]
                modifiers = re.split(",\s*", modifiers.replace(dimtext, "").strip())
                #modifiers.append("dimension")
            else:
                modifiers = re.split("[,\s]+", modifiers.strip())

            if "" in modifiers:
                modifiers.remove("")

        dtype = member.group("type")
        kind = member.group("kind")
        names = member.group("names")

        #If there are multiple vars defined on this line we need to return
        #a list of all of them.
        result = []

        #They might have defined multiple vars on the same line
        ready = self._separate_multiple_def(re.sub(",\s*", ", ", names.strip()))
        for name, ldimension, default, D in self._clean_multiple_def(ready):
            #Now construct the element and set all the values, then add it in the results list.
            udim = ldimension if ldimension is not None else dimension
            result.append(ValueElement(name, modifiers, dtype, kind, default, udim, parent, D))

        return result

    def _separate_multiple_def(self, defstring):
        """Separates the text after '::' in a variable definition to extract all the variables,
        their dimensions and default values.
        """
        import pyparsing
        nester = pyparsing.nestedExpr('(', ')')
        #parsed = nester.parseString("(" + defstring.replace("=", " = ") + ")").asList()[0]
        parsed = nester.parseString("(" + re.sub("=(>?)", " =\\1 ", defstring) + ")").asList()[0]
        i = 0
        clean = []
        while i < len(parsed):
            if (isinstance(parsed[i], str) and not re.match("=>?", parsed[i]) and 
                i+1 < len(parsed) and isinstance(parsed[i+1], list)):
                clean.append((parsed[i], parsed[i+1]))
                i += 2
            elif isinstance(parsed[i], str) and parsed[i] == ",":
                i += 1
            else:
                clean.append(parsed[i])
                i += 1

        #Now pass through again to handle the default values.
        i = 0
        ready = []
        while i < len(clean):
            if isinstance(clean[i], str) and re.match("=>?", clean[i]):
                ready.pop()
                if ">" in clean[i]:
                    ready.append([clean[i-1], ("> " + clean[i+1][0], clean[i+1][1])])
                else:
                    ready.append([clean[i-1], clean[i+1]])
                i += 2
            else:
                ready.append(clean[i])
                i += 1

        return ready

    def _collapse_default(self, entry):
        """Collapses the list structure in entry to a single string representing the default
        value assigned to a variable or its dimensions.
        """
        if isinstance(entry, tuple) or isinstance(entry, list):
            sets = []
            i = 0
            while i < len(entry):
                if isinstance(entry[i], str) and i+1 < len(entry) and isinstance(entry[i+1], list):
                    sets.append((entry[i], entry[i+1]))
                    i += 2
                elif isinstance(entry[i], str) and entry[i] == ",":
                    i += 1
                else:
                    sets.append((entry[i],))
                    i += 1

            result = []
            for s in sets:
                if isinstance(s[0], str):
                    name = s[0].strip(",")
                elif len(s) == 1:
                    name = self._collapse_default(s[0])
                    
                if len(s) > 1:
                    args = self._collapse_default(s[1])
                else:
                    args = []
                if len(args) > 0:
                    result.append("{}({})".format(name, args))
                else:
                    result.append(name)

            return ', '.join(result)
        else:
            if "," in entry:
                return entry.split(",")[0].strip()
            else:
                return entry.strip()

    def _count_dimensions(self, entry):
        """Counts the number of dimensions from a nested list of dimension assignments
        that may include function calls.
        """
        result = 0
        for e in entry:
            if isinstance(e, str):
                result += len(e.strip(",").split(","))
        return result

    def _clean_multiple_def(self, ready):
        """Cleans the list of variable definitions extracted from the definition text to
        get hold of the dimensions and default values.
        """
        result = []
        for entry in ready:
            if isinstance(entry, list):
                #This variable declaration has a default value specified, which is in the
                #second slot of the list.
                default = self._collapse_default(entry[1])
                #For hard-coded array defaults, add the parenthesis back in.
                if default[0] == "/":
                    default = "({})".format(default)
                namedim = entry[0]
            else:
                default = None
                namedim = entry

            if isinstance(namedim, str):
                name = namedim.strip().strip(",")
                dimension = None
                D = 0
            else:
                #Namedim is a tuple of (name, dimension)
                name = namedim[0].strip()
                D = self._count_dimensions(namedim[1])
                dimension = self._collapse_default(namedim[1])

            result.append((name, dimension, default, D))
        return result        

    def _get_dim_modifier(self, modifiers):
        """Extracts the dimension information from the string of modifiers extracted by
        the regex.
        
        :arg modifiers: the list of modifiers identified by the regex.
        """
        suffix = modifiers.split("dimension")[1]
        start = modifiers.index("dimension") + len("dimension")
        
        #We use a stack to monitor how many parenthesis we have traversed in the string.
        #Once we reach the closing parenthesis, we know that we have the dimension info.
        stack = []
        args = []
        for i in range(len(suffix)):
            if suffix[i] == '(':
                stack.append(i + start)
            elif suffix[i] == ')':
                args.append((stack.pop(), i + start))
                if len(stack) == 0:
                    #The last entry in args should be the indices of the entire
                    #dimension expression once the very first '(' has its twin found.
                    return args[-1]
