import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectsSectionLayout } from "./ProjectsSectionLayout";
import type { NavTreeNode } from "@/api/reports";
import { TooltipProvider } from "@/design-system";
import { useSidebarStore } from "@/store/sidebarStore";

// Team 1 > RWCA > Michael Group, the example the hierarchy was specified with.
const tree: NavTreeNode[] = [
  {
    id: "ws-1",
    type: "workspace",
    label: "Team 1",
    team_id: 1,
    children: [
      {
        id: "ws-1-sub-5",
        type: "sub_workspace",
        label: "RWCA",
        client_id: 5,
        board_query: { client: 5 },
        children: [
          {
            id: "project-9",
            type: "project",
            label: "Michael Group",
            project_key: "Michael",
            children: [],
          },
        ],
      },
      {
        id: "ws-1-sub-6",
        type: "sub_workspace",
        label: "Acme",
        client_id: 6,
        board_query: { client: 6 },
        children: [
          {
            id: "project-10",
            type: "project",
            label: "Tasks without a project",
            project_key: "Acme",
            is_client_tasks: true,
            children: [],
          },
        ],
      },
    ],
  },
  { id: "ws-2", type: "workspace", label: "Team 2", team_id: 2, children: [] },
];

vi.mock("@/api/reports", () => ({
  useNavTree: () => ({ data: tree, isLoading: false }),
}));
const dialogs: Record<string, unknown> = {};
vi.mock("./CreateProjectDialog", () => ({
  CreateProjectDialog: (props: { open: boolean; defaultClientId?: number }) => {
    dialogs.project = props;
    return props.open ? (
      <div role="dialog">
        Create project in {props.defaultClientId ?? "nowhere"}
      </div>
    ) : null;
  },
}));
vi.mock("./CreateClientDialog", () => ({
  CreateClientDialog: (props: { open: boolean; defaultTeamId?: number }) =>
    props.open ? (
      <div role="dialog">
        New sub-workspace in {props.defaultTeamId ?? "nowhere"}
      </div>
    ) : null,
}));

function Where() {
  const { pathname, search } = useLocation();
  return <div data-testid="where">{`${pathname}${search}`}</div>;
}

function renderTree() {
  return render(
    <TooltipProvider>
      <MemoryRouter initialEntries={["/projects"]}>
        <Routes>
          <Route path="/projects" element={<ProjectsSectionLayout />}>
            <Route index element={<Where />} />
            <Route path="*" element={<Where />} />
          </Route>
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </TooltipProvider>,
  );
}

describe("Projects tree: Workspace > Sub-workspace > Project", () => {
  beforeEach(() =>
    useSidebarStore.setState((s) => ({
      open: { ...s.open, projectsTree: true },
    })),
  );

  it("shows the hierarchy in order, top down", async () => {
    renderTree();
    expect(
      screen.getByText("Workspace › Sub-workspace › Project"),
    ).toBeInTheDocument();
    expect(screen.getByText("Team 1")).toBeInTheDocument();
    expect(screen.queryByText("RWCA")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Team 1"));
    expect(screen.getByText("RWCA")).toBeInTheDocument();
    await userEvent.click(screen.getByText("RWCA"));
    await userEvent.click(screen.getByText("Michael Group"));
    expect(screen.getByTestId("where")).toHaveTextContent("/projects/Michael");
  });

  it("finds a project by name and opens a sub-workspace task list", async () => {
    renderTree();
    await userEvent.type(
      screen.getByRole("textbox", {
        name: "Search workspaces, sub-workspaces and projects",
      }),
      "michael",
    );
    expect(screen.getByText("Michael Group")).toBeInTheDocument();
    expect(screen.queryByText("Acme")).not.toBeInTheDocument();
    await userEvent.clear(
      screen.getByRole("textbox", {
        name: "Search workspaces, sub-workspaces and projects",
      }),
    );
    await userEvent.click(screen.getByText("Team 1"));
    await userEvent.click(screen.getByText("Acme"));
    await userEvent.click(screen.getByText("Tasks without a project"));
    expect(screen.getByTestId("where")).toHaveTextContent("/projects/Acme");
  });

  it("adds a project to a sub-workspace and a sub-workspace to a workspace from their rows", async () => {
    renderTree();
    await userEvent.click(
      screen.getByRole("button", { name: "New sub-workspace in Team 1" }),
    );
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "New sub-workspace in 1",
    );
    expect(screen.queryByText("RWCA")).not.toBeInTheDocument(); // the row's button does not expand it
  });

  it("opens a workspace, and a sub-workspace board filtered to it", async () => {
    renderTree();
    await userEvent.click(screen.getByText("Team 2")); // empty: nothing to expand, so it opens
    expect(screen.getByTestId("where")).toHaveTextContent("/workspaces/2");
  });

  it("starts a project in the sub-workspace it was created from", async () => {
    renderTree();
    await userEvent.click(screen.getByText("Team 1"));
    await userEvent.click(
      screen.getByRole("button", { name: "New project in RWCA" }),
    );
    expect(screen.getByRole("dialog")).toHaveTextContent("Create project in 5");
    await userEvent.click(
      screen.getByRole("button", { name: "All tasks in RWCA" }),
    );
    expect(screen.getByTestId("where")).toHaveTextContent(
      "/projects/all-issues?client=5",
    );
  });
});
