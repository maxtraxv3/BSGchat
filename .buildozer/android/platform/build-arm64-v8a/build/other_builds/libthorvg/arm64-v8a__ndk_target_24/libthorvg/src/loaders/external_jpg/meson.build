source_file = [
   'tvgJpgLoader.h',
   'tvgJpgLoader.cpp',
]

jpg_inc = include_directories(get_option('jpg_include_dir'))
jpg_lib = cc.find_library('turbojpeg', dirs: [get_option('jpg_lib_dir')], required: true)
jpg_dep = declare_dependency(
  include_directories: jpg_inc,
  dependencies: [jpg_lib]
)

if jpg_dep.found()
    subloader_dep += [declare_dependency(
        include_directories : include_directories('.'),
        dependencies : jpg_dep,
        sources : source_file
    )]
endif
