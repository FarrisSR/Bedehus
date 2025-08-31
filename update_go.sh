# Rot-modul (hvis go.mod finnes)
if [ -f go.mod ]; then
  go version
  go mod tidy
  # Oppgrader bare patch/minor på alle direkte deps
  go get -u=patch ./...
  # Alternativt full minor/major: go get -u ./...
  go mod tidy
  # Sjekk sårbarheter:
  go install golang.org/x/vuln/cmd/govulncheck@latest
  govulncheck ./...
fi

# go/-underkatalog som egen modul
if [ -f go/go.mod ]; then
  (cd go && go mod tidy && go get -u=patch ./... && go mod tidy && govulncheck ./...)
fi
