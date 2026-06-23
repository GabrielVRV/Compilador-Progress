/*------------------------------------------------------------------------
  compile.p  —  usado pela ABL Deploy CLI

  Compila um fonte .p/.w/.cls e grava o .r em um diretório de saída.
  Os parâmetros chegam via -param "<fonte>|<dir_saida>|<propath>".

  Saída (stdout, capturada pela CLI):
    COMPILE-OK <fonte>
  ou
    COMPILE-ERROR
    <mensagem 1>
    <mensagem 2>
    ...

  O processo encerra com QUIT em ambos os casos; a CLI decide o sucesso
  pela presença de "COMPILE-OK" na saída.
------------------------------------------------------------------------*/

DEFINE VARIABLE cParam   AS CHARACTER NO-UNDO.
DEFINE VARIABLE cSource  AS CHARACTER NO-UNDO.
DEFINE VARIABLE cOutDir  AS CHARACTER NO-UNDO.
DEFINE VARIABLE cPropath AS CHARACTER NO-UNDO.
DEFINE VARIABLE iMsg     AS INTEGER   NO-UNDO.

ASSIGN cParam = SESSION:PARAMETER.

ASSIGN
    cSource  = ENTRY(1, cParam, "|")
    cOutDir  = ENTRY(2, cParam, "|")
    cPropath = IF NUM-ENTRIES(cParam, "|") >= 3 THEN ENTRY(3, cParam, "|")
               ELSE "".

/* Prefixa o PROPATH informado, mantendo o atual */
IF cPropath <> "" THEN
    ASSIGN PROPATH = cPropath + "," + PROPATH.

COMPILE VALUE(cSource) SAVE INTO VALUE(cOutDir) NO-ERROR.

IF COMPILER:ERROR OR ERROR-STATUS:ERROR THEN DO:
    PUT UNFORMATTED "COMPILE-ERROR" SKIP.
    PUT UNFORMATTED "  arquivo: " cSource SKIP.
    IF COMPILER:ERROR THEN
        PUT UNFORMATTED "  linha:   " COMPILER:ERROR-ROW
            " coluna: " COMPILER:ERROR-COLUMN SKIP.
    DO iMsg = 1 TO ERROR-STATUS:NUM-MESSAGES:
        PUT UNFORMATTED "  " ERROR-STATUS:GET-MESSAGE(iMsg) SKIP.
    END.
    QUIT.
END.

PUT UNFORMATTED "COMPILE-OK " cSource SKIP.
QUIT.
