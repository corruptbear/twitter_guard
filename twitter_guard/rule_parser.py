from pyparsing import (
    Word,
    nums,
    alphas,
    one_of,
    opAssoc,
    infixNotation,
    Literal,
    CaselessLiteral,
    ParserElement,
)

ParserElement.enablePackrat()

class EvalOperand:
    "Class to evaluate a parsed constant or variable"
    vars_ = {}

    def __init__(self, tokens):
        self.value = tokens[0]

    def eval(self):
        if self.value in EvalOperand.vars_:
            return EvalOperand.vars_[self.value]
        else:
            return eval(self.value)


def operatorOperands(tokenlist):
    "generator to extract operators and operands in pairs"
    it = iter(tokenlist)
    while 1:
        try:
            yield (next(it), next(it))
        except StopIteration:
            break

class EvalMultOp:
    "Class to evaluate multiplication and division expressions"

    def __init__(self, tokens):
        self.value = tokens[0]

    def eval(self):
        prod = self.value[0].eval()
        for op, val in operatorOperands(self.value[1:]):
            if op == "*":
                prod *= val.eval()
            if op == "/":
                prod /= val.eval()
        return prod


class EvalAddOp:
    "Class to evaluate addition and subtraction expressions"

    def __init__(self, tokens):
        self.value = tokens[0]

    def eval(self):
        s = self.value[0].eval()
        for op, val in operatorOperands(self.value[1:]):
            if op == "+":
                s += val.eval()
            if op == "-":
                s -= val.eval()
        return s

class EvalAndOp:
    "Class to evaluate and"

    def __init__(self, tokens):
        self.value = tokens[0]

    def eval(self):
        c = self.value[0].eval()
        for op, val in operatorOperands(self.value[1:]):
            c = c and val.eval()
        return c

class EvalOrOp:
    "Class to evaluate or"

    def __init__(self, tokens):
        self.value = tokens[0]

    def eval(self):
        c = self.value[0].eval()
        for op, val in operatorOperands(self.value[1:]):
            c = c or val.eval()
        return c


class EvalNotOp:
    "Class to evaluate not"

    def __init__(self, tokens):
        #the first element in the tokens list is !/not, the next is the thing to be negated
        self.value = tokens[0][1]

    def eval(self):
        return not self.value.eval()


class EvalComparisonOp:
    "Class to evaluate comparison expressions"
    opMap = {
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "!=": lambda a, b: a != b,
        "==": lambda a, b: a == b,
        "=": lambda a, b: a == b,
    }

    def __init__(self, tokens):
        self.value = tokens[0]

    def eval(self):
        val1 = self.value[0].eval()
        for op, val in operatorOperands(self.value[1:]):
            #print('EvalComparisonOp:',op,val)
            fn = EvalComparisonOp.opMap[op]
            val2 = val.eval()
            if fn(val1, val2) == False:
                return False
            val1 = val2
        else:
            #no break from the loop
            return True


def rule_eval(rule, vars_):
    """
    Evalute a logical expression with arithmatics and comparisons.
    
    Parameters:
    rule (str): a string representing
    vars_ (dict): a dictionary containing the names and the values of variables
    
    Returns:
    boolean: evaluation result.
    """

    variable = CaselessLiteral("followers_count") | CaselessLiteral("following_count") | CaselessLiteral("tweet_count") \
    | CaselessLiteral("media_count") | CaselessLiteral("default_profile_image") \
    | CaselessLiteral("days") | CaselessLiteral("favourites_count") | Word(alphas, exact=1)
    constant = Word(nums) | CaselessLiteral('True') | CaselessLiteral('False')
    operand = constant | variable 
    notop = CaselessLiteral("not") | Literal('!') 
    andop = CaselessLiteral("and") | Literal("&&") | Literal("&")
    orop = CaselessLiteral("or") | Literal("||") | Literal("|")
    multop = one_of("* /")
    plusop = one_of("+ -")


    #use the EvalOperand class to parse constants and variables
    operand.set_parse_action(EvalOperand)
    
    arith_expr = infixNotation(
        operand,
        [
            (multop, 2, opAssoc.LEFT, EvalMultOp),
            (plusop, 2, opAssoc.LEFT, EvalAddOp),
        ],
    )

    #define comparison expression
    comparison_op = one_of("> < >= <= == = !=")
    comp_expr = infixNotation(
        arith_expr,
        [
            (comparison_op, 2, opAssoc.LEFT, EvalComparisonOp),
        ],
    )

    #define logic expression
    logic_expr = infixNotation(
        comp_expr | CaselessLiteral('True') | CaselessLiteral('False'),
        [
            (notop, 1, opAssoc.RIGHT,EvalNotOp),
            (andop, 2, opAssoc.LEFT,EvalAndOp),
            (orop, 2, opAssoc.LEFT,EvalOrOp),
        ],
    )

    #pass variables to variable eval
    EvalOperand.vars_ = vars_
    
    return logic_expr.parse_string(rule)[0].eval()


def default_tests():  
    vars_ = {
        "A": 0,
        "B": 1,
        "C": 2,
        "D": 3,
        "E": 4,
        "F": 5,
    }

    exprs = [
        "not False",
        "A >= 0 and B >= 0",
        "2 <= D <= 1",
        "not (2 <= D <= 1) and E>D",
        "C >= 1 and 2 <= D <= 1",   
        "(A >= B) and (C <= D)",
        "A==0 and B==1 and C==2 or (D==3 and E==5)",  
        "A>F", 
        "A + B < 2",
        "3 >= F/C >=2",
        "((A+B)*(C+D) > 5) or ((F-E)>0) "
    ]

    tests = []
    for t in exprs:
        t_orig = t
        tests.append((t_orig, eval(t, vars_)))


    failed = 0
    for test, expected in tests:
        parsedvalue = rule_eval(test,vars_)
        print(test, 'expected:',expected, 'parsed:',parsedvalue)
        if parsedvalue!=expected:
            print("<<< FAIL")
            failed += 1
        else:
            print("")
    print('total failure:',failed)  

#print(rule_eval("(False != False)",{}))
#print(rule_eval( "! ! False",{}))
#print(rule_eval('True && True && False',{}))
#default_tests()