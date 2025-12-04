# IEC 61131-3 & Beremiz Domain Knowledge

Reference documentation for PLC error classification. Contains domain facts only—no prompt instructions.

---

## 1. Build Pipeline

```
PLCopen XML → Code Generation → IEC Compilation → C Compilation → SoftPLC Binary
  (input)      (Beremiz/Python)   (matiec/iec2c)     (gcc)          (output)
```

### Stage Detection Patterns

| Stage | Tool | Detection Patterns |
|-------|------|-------------------|
| **xml_validation** | lxml/XSD | `XSD schema`, `xs:dateTime`, `Missing child element`, `is not expected`, `attribute '...' is required` |
| **code_generation** | Beremiz Python | `Traceback`, `stderr: Traceback`, `File "...py"`, `AttributeError`, `TypeError`, `KeyError`, `IndexError`, `ValueError`, `PLCGenerator.py`, `ProjectController.py`, `PLCControler.py` |
| **iec_compilation** | matiec/iec2c | `iec2c`, `matiec`, `plc.st:`, `error:` with `line-col..line-col` format, `In section: PROGRAM`, `IEC to C compiler` |
| **c_compilation** | gcc | `gcc`, `g++`, `ld returned`, `undefined reference`, `.c:`, `.o:`, `collect2:`, `fatal error:`, `No such file or directory` |

### Log Structure

```
[timestamp]: Building project...
[timestamp]: Cannot build project.     ← Appears if ANY error occurs
stdout: Warning: PLC XML file...       ← XML validation (often cosmetic)
Generating SoftPLC IEC-61131...        ← Code generation starts

stderr: Traceback (most recent call last):   ← Python errors here
  File "/root/beremiz/PLCGenerator.py"...
AttributeError: ...

Compiling IEC Program into C code...   ← IEC compilation starts
"/root/beremiz/matiec/iec2c" ...
Warning: /path/plc.st:30-4..30-12: error: ...  ← IEC errors (line-col..line-col)
Error: IEC to C compiler returned 1

Compiling C Program to target ...      ← C compilation starts
file.c:(.text+0x...): undefined reference to `...'
collect2: error: ld returned 1 exit status
Error: C compilation of target failed.
```

---

## 2. Common Error Patterns

### IEC Compilation Errors (matiec/iec2c)

| Error Message | Root Cause | Typical Fix | Complexity |
|---------------|------------|-------------|------------|
| `Assignment to CONSTANT variables is not allowed` | Variable has `constant="true"` but code assigns to it | Remove `constant` attribute or remove assignment | trivial |
| `Undeclared variable 'X'` / `Variable not declared in this scope` | Variable used but not declared | Add to appropriate VAR section | trivial |
| `Incompatible data types for ':=' operation` | Type mismatch in assignment | Add type conversion or fix declaration | moderate |
| `Invalid data type for 'IF' condition` / `should be BOOL` | IF/WHILE/REPEAT condition not BOOL | Use comparison (e.g., `x > 0`) | moderate |
| `Function expects N arguments, got M` / `Invalid parameters` | Wrong argument count | Match function signature | trivial |
| `Invalid data type for 'FOR' control variable` | FOR loop variable not integer | Use INT/DINT for loop counter | trivial |
| `Numerical value exceeds range` | Integer/float overflow | Use larger data type or reduce value | trivial |
| `Invalid syntax for TIME/DATE data type` | Malformed time literal | Use correct format: `T#5s`, `D#2024-01-01` | trivial |
| `Duplicate parameter 'X' when invoking` | Same parameter passed twice | Remove duplicate | trivial |
| `Array variable not declared` / `Invalid data type for array subscript` | Array indexing error | Check array declaration and index type | moderate |

### Code Generation Errors (Beremiz Python)

| Error Message | Root Cause | Typical Fix | Complexity |
|---------------|------------|-------------|------------|
| `AttributeError: 'NoneType' object has no attribute 'upper'` | POU body is empty/None | Add code to POU body | moderate |
| `AttributeError: 'NoneType' object has no attribute '...'` | Missing required XML element | Add missing element | moderate |
| `KeyError: 'varName'` | Variable not in symbol table | Declare in interface | moderate |
| `TypeError: cannot unpack non-iterable` | Malformed XML structure | Fix XML structure | moderate |
| `IndexError: list index out of range` | Empty list access (e.g., no POUs) | Add required POU or check config | moderate |
| `"No body defined in 'X' POU"` | POU missing `<body>` element | Add body element with code | moderate |
| `"Undefined pou type 'X'"` | Invalid pouType attribute | Use `program`, `functionBlock`, or `function` | trivial |
| `"Undefined block type 'X' in 'Y' POU"` | Reference to unknown function block | Define or import the FB | complex |

### XML Validation Errors

| Error Message | Root Cause | Typical Fix | Complexity |
|---------------|------------|-------------|------------|
| `is not a valid value of xs:dateTime` | DateTime uses space not 'T' | Use `YYYY-MM-DDTHH:MM:SS` | trivial |
| `Missing child element(s)` | Required element missing | Add per PLCopen schema | moderate |
| `This element is not expected` / `Element not allowed` | Invalid element in context | Remove or relocate | moderate |
| `The attribute '...' is required but missing` | Required attribute missing | Add attribute to element | trivial |
| `'...' is not a valid value for attribute '...'` | Invalid attribute value | Use valid value per schema | trivial |
| `No matching global declaration` / `Cannot resolve namespace` | Wrong/missing namespace | Fix xmlns declaration | moderate |

### C Compilation Errors (gcc/ld)

| Error Message | Root Cause | Typical Fix | Complexity |
|---------------|------------|-------------|------------|
| `undefined reference to '__LOG_RECORD'` | LOG function unavailable | Remove LOG calls or configure runtime | complex |
| `undefined reference to '__INIT_EXTERNAL'` | External variable linkage | Verify VAR_EXTERNAL matches global | complex |
| `undefined reference to '...'` | Missing function/symbol definition | Add library or define function | moderate |
| `multiple definition of '...'` | Duplicate symbol across files | Remove duplicate definition | moderate |
| `implicit declaration of function` | Missing header/function prototype | Add #include or forward declaration | moderate |
| `fatal error: ...: No such file or directory` | Missing header file | Install library or fix include path | moderate |
| `ld returned 1 exit status` | Linker failed (see preceding errors) | Fix preceding undefined references | varies |

---

## 3. Cascading Error Patterns

One root cause often produces multiple error messages:

| Pattern | Explanation |
|---------|-------------|
| XML warning + later real error | XML schema warnings (like missing `<data>` child) are often cosmetic; real error is downstream |
| Multiple "undeclared variable" for same name | Single missing declaration causes all uses to error |
| Type error → expression errors | Type mismatch cascades to subsequent operations |
| Python NoneType errors | Usually means XML element expected by generator is missing/empty |

**Key insight**: Always identify the FIRST substantive error—later errors are often symptoms.

---

## 4. IEC 61131-3 Quick Reference

### POU Types

| Type | Has Memory | Returns Value | Use |
|------|------------|---------------|-----|
| `PROGRAM` | Yes | No | Main entry, binds to task |
| `FUNCTION_BLOCK` | Yes (per instance) | No | Reusable stateful logic |
| `FUNCTION` | No | Yes (single) | Pure calculations |

### Key Variable Sections

| Section | Purpose | Error Relevance |
|---------|---------|-----------------|
| `VAR` | Local variables | Most common |
| `VAR_INPUT` | Read-only inputs from caller | Type mismatch errors |
| `VAR_OUTPUT` | Outputs to caller | Type mismatch errors |
| `VAR_EXTERNAL` | Reference to global | Causes `undefined reference` in C compilation |

### CONSTANT Modifier

Variables with `constant="true"` cannot be assigned after initialization. This causes the common error: `Assignment to CONSTANT variables is not allowed`.

### Time/Date Literal Formats

These formats frequently cause `Invalid syntax` errors when malformed:

| Type | Format | Example |
|------|--------|---------|
| TIME | `T#<value><unit>` | `T#5s`, `T#100ms`, `T#1h30m` |
| DATE | `D#YYYY-MM-DD` | `D#2024-03-15` |
| TOD | `TOD#HH:MM:SS` | `TOD#14:30:00` |
| DT | `DT#YYYY-MM-DD-HH:MM:SS` | `DT#2024-03-15-14:30:00` |

---

## 5. PLCopen XML Essentials

**Namespace**: `http://www.plcopen.org/xml/tc6_0201`

**DateTime format**: Must use ISO 8601 with 'T' separator: `2024-03-15T10:30:00` (NOT `2024-03-15 10:30:00`)

**Valid pouType values**: `program`, `functionBlock`, `function`

**Minimal POU structure**:
```xml
<pou name="Main" pouType="program">
  <interface>
    <localVars><variable name="x"><type><INT/></type></variable></localVars>
  </interface>
  <body>
    <ST><xhtml:p xmlns:xhtml="http://www.w3.org/1999/xhtml">x := 1;</xhtml:p></ST>
  </body>
</pou>
```

Missing `<body>` or empty `<xhtml:p/>` causes code generation errors.
