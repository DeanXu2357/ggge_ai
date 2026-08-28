package server

func init() {
	register("init", func(s *Server) command { return s.commands.InitBattle })
	register("load", func(s *Server) command { return s.commands.Load })
	register("reach", func(s *Server) command { return s.commands.Reach })
	register("export", func(s *Server) command { return s.commands.Export })
	register("act", func(s *Server) command { return s.commands.Act })
	register("actions", func(s *Server) command { return s.commands.Actions })
	register("response_attacks", func(s *Server) command { return s.commands.ResponseAttacks })
}
