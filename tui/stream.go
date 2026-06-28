package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

func sanitizeHistory(history []turn) []turn {
	clean := make([]turn, 0, len(history))
	for _, item := range history {
		role := strings.TrimSpace(item.Role)
		content := strings.TrimSpace(item.Content)
		if content == "" {
			continue
		}
		if role != "user" && role != "assistant" {
			continue
		}
		clean = append(clean, turn{Role: role, Content: content})
	}
	return clean
}

func agentRequestBody(q string, history []turn, sessionID string, retry bool) ([]byte, error) {
	return json.Marshal(map[string]any{
		"question":   strings.TrimSpace(q),
		"history":    sanitizeHistory(history),
		"session_id": strings.TrimSpace(sessionID),
		"retry":      retry,
	})
}

func stream(ctx context.Context, backend, q string, history []turn, sessionID string, retry bool, sub chan tea.Msg) {
	body, _ := agentRequestBody(q, history, sessionID, retry)
	req, _ := http.NewRequestWithContext(ctx, "POST", backend+"/api/agent/stream", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		if ctx.Err() == nil { // not a user interrupt
			sub <- errMsg("无法连接后端 " + backend + ":" + err.Error())
		}
		sub <- doneMsg{}
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		sub <- errMsg(formatHTTPError(resp))
		sub <- doneMsg{}
		return
	}
	sc := bufio.NewScanner(resp.Body)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		line := sc.Text()
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		data := strings.TrimSpace(line[len("data:"):])
		if data == "[DONE]" {
			break
		}
		var ev struct {
			Type    string          `json:"type"`
			Payload json.RawMessage `json:"payload"`
			Meta    eventMeta       `json:"meta"`
		}
		if json.Unmarshal([]byte(data), &ev) != nil {
			continue
		}
		if !metaEmpty(ev.Meta) {
			sub <- nodePulseMsg{kind: ev.Type, meta: ev.Meta}
		}
		switch ev.Type {
		case "plan":
			var s []string
			json.Unmarshal(ev.Payload, &s)
			sub <- planMsg(s)
		case "text":
			var s string
			json.Unmarshal(ev.Payload, &s)
			sub <- textMsg(s)
		case "tool_call":
			var t struct {
				Name string         `json:"name"`
				Args map[string]any `json:"args"`
			}
			json.Unmarshal(ev.Payload, &t)
			sub <- toolCallMsg{name: t.Name, args: t.Args, meta: ev.Meta}
		case "tool_result":
			var t struct {
				Name   string `json:"name"`
				Result string `json:"result"`
			}
			json.Unmarshal(ev.Payload, &t)
			sub <- toolResultMsg{name: t.Name, result: t.Result, meta: ev.Meta}
		case "reflect":
			var s string
			json.Unmarshal(ev.Payload, &s)
			sub <- reflectMsg(s)
		case "final":
			var s string
			json.Unmarshal(ev.Payload, &s)
			sub <- finalMsg(s)
		case "error":
			var s string
			json.Unmarshal(ev.Payload, &s)
			sub <- errMsg(s)
		}
	}
	sub <- doneMsg{}
}

func listen(sub chan tea.Msg) tea.Cmd {
	return func() tea.Msg { return <-sub }
}

// ---- model ----
