package server

func init() {
	Register("init", func(s *Server) Handler { return s.commands.InitBattle })
	Register("load", func(s *Server) Handler { return s.commands.Load })
	Register("reach", func(s *Server) Handler { return s.commands.Reach })
	Register("export", func(s *Server) Handler { return s.commands.Export })
	Register("act", func(s *Server) Handler { return s.commands.Act })
	Register("actions", func(s *Server) Handler { return s.commands.Actions })
	Register("response_attacks", func(s *Server) Handler { return s.commands.ResponseAttacks })
}
