# Project Library information architecture

Project Library replaces the standalone Trash page while retaining every
lifecycle entry.

## Navigation and views

- Sidebar: Workspace and Project Library are primary destinations.
- Recent Projects: only current, favorite, and recent projects remain in the
  sidebar.
- Library filters: All, Active, Archived, Trash.
- View controls: search by name/location, sort by Modified/Name/Size, and switch
  between List and Grid.
- List is the default and exposes Name, Status, Modified or Deleted, Size,
  Location, and Actions.
- Grid is an optional visual browsing mode using the same mock model.

## Selection and actions

Selecting a row or card updates Project Details in the right Inspector. Mock
actions cover open directory, rename, duplicate, archive, unarchive/restore,
and permanent deletion. Destructive deletion still requires typed project-name
confirmation. All actions remain local display events and never touch disk.

At narrow widths the table preserves its column canvas and enables horizontal
scrolling, preventing field overlap or clipping without scaling the root UI.
