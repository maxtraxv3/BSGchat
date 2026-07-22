source_file = [
   'tvgPngLoader.h',
   'tvgPngLoader.cpp',
]

png_inc = include_directories(get_option('png_include_dir'))
png_lib = cc.find_library('png16', dirs: [get_option('png_lib_dir')], required: true)
png_dep = declare_dependency(
  include_directories: png_inc,
  dependencies: [png_lib]
)

if png_dep.found()
    subloader_dep += [declare_dependency(
        include_directories : include_directories('.'),
        dependencies : png_dep,
        sources : source_file
    )]
endif
