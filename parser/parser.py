from lexer import LexerToken, TokenType, Keywords, Lexer
from error import ErrorList, Error, ErrorType
from parser.source_location import SourceLocation
from parser.node import *

# peter parser

class Parser():
    def __init__(self, lexer):
        self.lexer = lexer
        self.token_index = 0
        self._current_token = self.next_token()
        self.error_list = ErrorList()
        
        self.source_location = lexer.source_location

        self.keyword_methods = {
            'let': self.parse_variable_declaration,
            'if': self.parse_if_statement,
            'func': self.parse_func_declaration,
            'import': self.parse_import,
            'return': self.parse_return,
            'while': self.parse_while,
            'for': self.parse_for
        }

    @property
    def filename(self):
        return self.source_location.filename
    
    @property
    def current_token(self):
        if self._current_token is None:
            return LexerToken.NONE

        return self._current_token
    
    def expect_token(self, token_type, offset=0, token=None):
        # if no token passed in, peek from offset
        if token == None:
            token = self.peek_token(offset)

        if token.type == token_type:
            return token
        else:
            self.error('expected {0} but recieved {1}'.format(token_type.name, token.type.name))
            return None
    
    def next_token(self):
        # check if next index is past list boundaries
        if self.token_index+1 > len(self.lexer.tokens):
            return None
            
        # return selected token, increment index
        self._current_token = self.lexer.tokens[self.token_index]
        self.token_index += 1
        
        return self.current_token
    
    # return token at token.index + offset
    def peek_token(self, offset=1, expected_type=None):
        # check bounds
        if self.token_index+offset-1 > len(self.lexer.tokens):
            return None
            
        token = self.lexer.tokens[self.token_index+offset-1]
        
        # check type if expected_type != None
        if expected_type != None and token.type != expected_type:
            return None
        
        return token
    
    def error(self, message):
        # tokens have locations attached from the lexer, pass to self.error
        # if an error occurs
        location = self.current_token.location

        self.error_list.push_error(Error(ErrorType.Syntax, location, message, self.filename))

    # read next token and error if token.type != passed in token type
    def eat(self, token_type=None):
        if token_type is not None:
            if self.expect_token(token_type) is None:
                return None

        self._current_token = self.next_token()

        return self.current_token
    
    # parse reference to a variable
    def parse_variable(self):
        # create variable node and eat identifier
        variable_node = NodeVariable(self.current_token)

        self.eat(TokenType.Identifier)
        
        return variable_node
   
    def parse_member_expression(self, lhs):
        if self.eat(TokenType.Dot) is None:
            return None

        token = self.current_token

        # expect identifier for right hand side
        rhs_name = self.peek_token(0, expected_type=TokenType.Identifier)

        if rhs_name is None:
            self.error('invalid member access: must be in format <expression>.<identifier>')
            return None

        self.eat(TokenType.Identifier)

        return NodeMemberExpression(lhs, rhs_name, token)
   
    def parse_array_access_expression(self, lhs):
        if self.eat(TokenType.LBracket) is None:
            return None

        token = self.current_token

        # get internal expr
        access_expr = self.parse_expression()

        if access_expr is None:
            self.error('invalid array access expression')
            return None

        if self.eat(TokenType.RBracket) is None:
            return None

        return NodeArrayAccessExpression(lhs, access_expr, token)
        
    def import_file(self, filename, filename_token=None):
        try:
            fp = open(filename, 'r')
        except FileNotFoundError:
            self.error('source file \'{}\' does not exist'.format(filename))
            return None
                
        data = fp.read()
        
        # lex loaded file data
        source_location =  SourceLocation(filename)

        lexer = Lexer(data, source_location)
        lexer.lex()
        
        parser = Parser(lexer)
        
        # an import node acts similar to a block and holds all variables and functions
        # in a tree. A parser is passed for getting various information in the interpreter
        if filename_token == None:
            filename_token = LexerToken(f'"{filename}"')
        
        node = NodeImport(filename_token, source_location)
        node.children = parser.get_statements()

        for error in parser.error_list.errors:
            self.error_list.push_error(error)
        
        return node
        
    def parse_while(self):
        # eat while keyword
        token = self.current_token
        if not self.eat(TokenType.Keyword):
            return None

        expression = self.parse_expression()

        if expression == None:
            return None

        block = self.parse_block_statement()

        if block == None:
            return None
        
        return NodeWhile(expression, block, token)

    def parse_for(self):
        # eat for keyword
        token = self.current_token
        if not self.eat(TokenType.Keyword):
            return None

        # get var name of iter
        var_token = self.current_token
        self.eat(TokenType.Identifier)
        if var_token is None:
            return None

        # eat in keyword
        in_keyword = self.current_token
        self.eat(TokenType.Keyword)
        if in_keyword is None or in_keyword.value != 'in':
            self.error('for loop expects syntax `for <var> in <expr> { ... }`')
            return None

        expression = self.parse_expression()
        if expression == None:
            return None

        block = self.parse_block_statement()

        if block == None:
            return None

        return NodeFor(var_token, expression, block, token)
        
    def parse_import(self):
        self.eat(TokenType.Keyword)
        
        filename = None
        filename_token = self.current_token
        
        # check for path after import
        self.expect_token(TokenType.String, token=filename_token)
        
        # trim off ""
        filename = self.current_token.value[1:-1]
        self.eat(TokenType.String)
        return self.import_file(filename, filename_token)
        
    def parse_return(self):
        self.eat(TokenType.Keyword)
        value_node = self.parse_expression()
        return NodeFunctionReturn(value_node, self.current_token)

    def parse_assignment_statement(self, node, require_operator=True):
        # operator would be '=' or '+=', '-=', etc.
        if require_operator:
            self.eat()
    
        if self.current_token.type == TokenType.LParen:
            value = self.parse_parenthesis()
        else:
            value = self.parse_expression()

        if value is None:
            self.error('Invalid assignment')
            return None

        node = NodeAssign(node, value)
        
        return node
    
    def parse_parenthesis(self):
        # eat open parenthesis
        self.eat(TokenType.LParen)

        argument_list = None

        if self.current_token in (TokenType.RParen, TokenType.Identifier):
            expr = self.parse_expression()
            self.expect_token(TokenType.RParen)
            return expr
        
        # function declaration with no arguments, skip all argument checks and create empty arg list
        elif self.peek_token(0, expected_type=TokenType.RParen):
            argument_list = NodeArgumentList([], self.current_token)
            
        # function definition with arguments
        else:
            arguments = []
            has_vargs = False

            while True:
                if has_vargs:
                    self.error('Arguments provided after variadic arguments')
                    break

                is_vargs = False

                if self.peek_token(0, TokenType.Multiply):
                    is_vargs = True
                    has_vargs = True

                if self.expect_token(TokenType.Identifier) is None:
                    self.error('invalid argument format')
                    break

                # parse declaration(vname:type) without let keyword
                argument = self.parse_variable_declaration(require_keyword=False)
                
                if argument is None:
                    self.error('invalid argument')
                    break

                arguments.append(argument)

                if self.peek_token(0, expected_type=TokenType.Comma):
                    # eat comma and continue on with argument list
                    self.eat(TokenType.Comma)
                else:
                    break
                    
            argument_list = NodeArgumentList(arguments, self.current_token)
        
        if argument_list is None:
            self.error('invalid argument list')
            return None
        
        # eat closing parenthesis
        self.eat(TokenType.RParen)
            
        return self.parse_function_expression(argument_list)

    def parse_statement(self):
        token = self.current_token
        
        # empty statement, eat semicolon and try again
        if token.type == TokenType.Semicolon:
            self.eat(TokenType.Semicolon)
            return self.parse_statement()
            
        if token.type == TokenType.Keyword:
            node = self.parse_keyword()

            if node is None:
                return None
            
            # check if node is function block, exempt from semicolon
            if node.type == NodeType.Declare and (node.value is not None and node.value.type == NodeType.Assign):
                rhs = node.value.value
                if rhs.type == NodeType.FunctionExpression:
                    return node
            
            if node.type in (NodeType.IfStatement, NodeType.While, NodeType.For):
                return node
        else:
            node = self.parse_expression()
            
            if node is None:
                self.error('Unknown token {} in statement'.format(token.type))
                node = None
        
        if self.current_token.type != TokenType.Semicolon:
            self.error('Missing semicolon (found {})'.format(self.current_token.type.name))
        # eat semicolon at end of statement
        self.eat(TokenType.Semicolon)
            
        return node
    
    def get_statements(self):
        if self.current_token.type == TokenType.RBrace or self.current_token.type == TokenType.NoneToken:
            return []

        statements = [self.parse_statement()]
        
        # read until no statements left
        while self.current_token != None:
            # We hit last statement in block, break
            if self.current_token.type in (TokenType.RBrace, TokenType.NoneToken):
                break
                
            statement = self.parse_statement()
            # parse statement and skip to next semicolon
            statements.append(statement)

        return statements

    def parse_keyword(self):
        keyword = self.expect_token(TokenType.Keyword)

        method = None
        
        if keyword is not None:
            method = self.keyword_methods[keyword.value]

        if method is None:
            self.error('{0} is not a valid keyword'.format(keyword))

        return method()

    def parse_block_statement(self):
        self.eat(TokenType.LBrace)
        block = NodeBlock(self.current_token)
        block.children = self.get_statements()
        self.eat(TokenType.RBrace)

        return block

    def parse_array_expression(self):
        members = []
    

        # eat left bracket
        if self.eat(TokenType.LBracket) is None:
            return None

        token = self.current_token

        while token.type != TokenType.RBracket:
            # parse expr
            item_expr = self.parse_expression()

            if item_expr is None:
                self.error('invalid array member item {}'.format(self.current_token))
                return None

            members.append(item_expr)

            if self.current_token.type == TokenType.Comma:
                self.eat(TokenType.Comma)
            else:
                break

        if self.eat(TokenType.RBracket) is None:
            return None

        return NodeArrayExpression(members, token)

    def parse_object_expression(self):
        members = [] # array of var declarations

        # eat left brace
        if self.eat(TokenType.LBrace) is None:
            return None

        token = self.current_token

        # find all lines in block
        while token.type != TokenType.RBrace:
            # parse variable declaration
            var_decl = self.parse_variable_declaration(False)

            if var_decl is None:
                self.error('invalid object member declaration')
                return None

            members.append(var_decl)

            token = self.current_token

        if self.eat(TokenType.RBrace) is None:
            return None

        return NodeObjectExpression(members)

    def parse_type(self):
        node = NodeVarType(self.current_token)
        self.eat()
        return node
        
    def parse_function_call(self, node):        
        self.eat(TokenType.LParen)
        
        argnames = []
        arg = None
        last = self.current_token
        
        if self.current_token.type is not TokenType.RParen:
            # skip until RParen
            while self.current_token.type != TokenType.RParen:
                # append argument to ArgumentList node
                argnames.append(self.parse_expression())
                if self.current_token.type == TokenType.RParen:
                    break
                self.eat()
                if self.current_token.type == TokenType.NoneToken:
                    return NodeNone(last)
        
        # eat closing paren
        self.eat(TokenType.RParen)

        args = NodeArgumentList(argnames, self.current_token)
        
        return NodeCall(node, args)

    def parse_function_expression(self, argument_list=None):
        if argument_list is None:
            argument_list = self.parse_parenthesis()
        block = self.parse_block_statement()
        return NodeFunctionExpression(argument_list, block)
    
    def parse_func_declaration(self):
        # func NAME(...) { ... }
        
        # eat func keyword
        type = self.current_token
        self.eat(TokenType.Keyword)
        # eat function name
        name = self.current_token
        if self.eat(TokenType.Identifier) is None:
            return None
        
        # parse assignment, parenthesis, etc.
        val_node = self.parse_assignment_statement(NodeVariable(name), require_operator=False)
        type_node = NodeVarType(type)
        node = NodeDeclare(type_node, name, val_node)
        
        return node
    
    def parse_variable_declaration(self, require_keyword=True):
        # let VARNAME:TYPE parse_assignment_statement
        
        if require_keyword:
            # eat let keyword
            if self.eat(TokenType.Keyword) is None:
                return None
        elif self.peek_token(0, expected_type=TokenType.Keyword) and self.peek_token(0).value == 'func':
            return self.parse_func_declaration()
            
        name = self.current_token
        if self.eat(TokenType.Identifier) is None:
            return None

        type_node = None
        
        # manual type set
        if self.current_token.type == TokenType.Colon:
            self.eat(TokenType.Colon)
            type_node_token = self.current_token
            type_node = self.parse_factor()

            if type_node is None or (not isinstance(type_node, NodeVariable) and not isinstance(type_node, NodeMemberExpression)):
                self.error('Declaration type should either be an identifier or member access, got {}'.format(type_node_token))
                return None

        if self.current_token.type == TokenType.Equals:
            val_node = self.parse_assignment_statement(NodeVariable(name))
        else:
            val_node = NodeNone(name)

        # TODO: multiple variable declaration(e.g let var0,var1)
        vnodes = NodeDeclare(type_node, name, val_node)
        
        return vnodes

    def parse_if_statement(self):
        # eat `if`
        if_token = self.current_token
        if self.eat(TokenType.Keyword) is None:
            return None

        expr = self.parse_expression()

        if expr is None:
            return None

        block = self.parse_block_statement()

        if block is None:
            return None

        else_block = None
        
        token = self.current_token

        if token.type == TokenType.Keyword:
            if Keywords(token.value) == Keywords.Else:
                # eat else
                self.eat(TokenType.Keyword)
                else_block = self.parse_block_statement()
            elif Keywords(token.value) == Keywords.Elif:
                else_block = self.parse_if_statement()
        
        return NodeIfStatement(expr, block, else_block, if_token)
    
    def parse_factor(self):
        # handles value or (x ± x)
        token = self.current_token

        node = None
        
        # handle +, -
        if token.type in (TokenType.Plus, TokenType.Minus):
            self.eat(token.type)
            node = NodeUnaryOp(token, self.parse_factor())
        
        # handle '!'
        elif token.type == TokenType.Not:
            self.eat(TokenType.Not)
            node = NodeUnaryOp(token, self.parse_factor())
            
        elif token.type == TokenType.Number:
            self.eat(TokenType.Number)
            node = NodeNumber(token)
        
        elif token.type == TokenType.String:
            self.eat(TokenType.String)
            node = NodeString(token)
        
        elif token.type == TokenType.LParen:
            self.eat(TokenType.LParen)
            node = self.parse_expression()
            self.eat(TokenType.RParen)
        elif token.type == TokenType.LBracket:
            node = self.parse_array_expression()
        elif token.type == TokenType.LBrace:
            node = self.parse_object_expression()
        elif token.type == TokenType.Identifier:
            node = self.parse_variable()


        while node != None and self.current_token.type in (TokenType.Dot, TokenType.LParen, TokenType.LBracket):
            if self.peek_token(0, expected_type=TokenType.Dot):
                node = self.parse_member_expression(node)
            elif self.peek_token(0, expected_type=TokenType.LBracket):
                node = self.parse_array_access_expression(node)
            elif self.peek_token(0, expected_type=TokenType.LParen):
                node = self.parse_function_call(node)

        return node

    def parse_term(self):
        # handles multiply, division, expressions
        node = self.parse_factor()
        while self.current_token.type in (TokenType.Multiply, TokenType.Divide):
            token = self.current_token
            if token.type == TokenType.Multiply:
                self.eat(TokenType.Multiply)
            elif token.type == TokenType.Divide:
                self.eat(TokenType.Divide)
            node = NodeBinOp(left=node, token=token, right=self.parse_factor())
        return node
    
    def parse_expression(self):
        node = self.parse_term()
        
        multiop_types = (
            TokenType.PlusEquals, TokenType.MinusEquals, 
            TokenType.MultiplyEquals, TokenType.DivideEquals
        )
        
        expected_types = (
            TokenType.Equals,
            TokenType.Plus, TokenType.Minus,
            TokenType.BitwiseOr, TokenType.BitwiseAnd, TokenType.BitwiseXor,
            TokenType.Compare, TokenType.NotCompare,
            TokenType.Spaceship,
            TokenType.LessThan, TokenType.GreaterThan,
            TokenType.LessThanEqual, TokenType.GreaterThanEqual
        ) + multiop_types

        while self.current_token.type in expected_types:
            token = self.current_token
        
            if self.peek_token(0, expected_type=TokenType.Equals):
                node = self.parse_assignment_statement(node)
                continue
                
            if self.current_token.type in multiop_types:
                # parse (lhs [operator] rhs) and return assign node
                assign_node = self.parse_assignment_statement(node)
                
                # this is slightly sketchy, but also will be able to handle
                # operations like <<= and any other multichar operation
                operation = LexerToken(token.value.strip('='))
                
                # make value (lhs [operator] rhs)
                value_node = NodeBinOp(left=NodeVariable(assign_node.lhs), token=operation, right=assign_node.value)
                
                # final node should be (lhs [=] lhs [operator] rhs)
                assign_node.value = value_node
                node = assign_node
                continue
                
            if token.type in expected_types:
                self.eat()
                
            node = NodeBinOp(left=node, token=token, right=self.parse_term())
        return node
        
    def parse(self):
        return self.get_statements()
