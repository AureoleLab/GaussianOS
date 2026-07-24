# ModernUI pages

The production page roots currently live in `Main.qml` as the animated
Workspace and Project Library hosts.  Page-specific visual content is factored
into `components/ViewerPane.qml` and `components/ProjectLibrary.qml`; this
directory is reserved for extracting those roots without changing the shared
Python backend contract.
