package main

import (
	"go/parser"
	"go/token"
	"io/fs"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

const modulePath = "github.com/DeanXu2357/ggge_ai/engine"

func isStandardLibrary(path string) bool {
	first, _, _ := strings.Cut(path, "/")
	return !strings.Contains(first, ".")
}

func isOwnPackage(path string) bool {
	return path == modulePath || strings.HasPrefix(path, modulePath+"/")
}

func TestTheEngineImportsNoModuleOutsideTheStandardLibrary(t *testing.T) {
	fileSet := token.NewFileSet()
	walk := func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if entry.Name() == "testdata" || entry.Name() == "vendor" {
				return fs.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(entry.Name(), ".go") {
			return nil
		}
		file, err := parser.ParseFile(fileSet, path, nil, parser.ImportsOnly)
		if err != nil {
			return err
		}
		for _, spec := range file.Imports {
			imported, err := strconv.Unquote(spec.Path.Value)
			if err != nil {
				return err
			}
			if isStandardLibrary(imported) || isOwnPackage(imported) {
				continue
			}
			t.Errorf("%s imports %q: the engine reads its data from the payload, "+
				"and it links no module outside the standard library", path, imported)
		}
		return nil
	}
	if err := filepath.WalkDir(".", walk); err != nil {
		t.Fatalf("walk the engine: %v", err)
	}
}
