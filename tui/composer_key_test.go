package main

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestKeyRunesReachComposer(t *testing.T) {
	m := initialModel()
	m.ready = true
	km := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("hello")}
	m2, _ := m.updateKey(km)
	if m2.ti.Value() != "hello" {
		t.Fatalf("字符未进入 composer: %q", m2.ti.Value())
	}
}
